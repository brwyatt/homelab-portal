"""Configuration loader and schema models for Homelab Portal."""
from __future__ import annotations

from typing_extensions import override
import ipaddress
import os
import re
from pathlib import Path
import yaml
from pydantic import BaseModel, Field, field_validator


class UIConfig(BaseModel):
    title: str = "Homelab Portal"
    subtitle: str | None = "Services & Resources"
    theme: str = "fiber-optic"
    custom_themes_dir: str | None = None
    show_search: bool = True
    show_network_badge: bool = True
    show_user_badge: bool = True
    footer_text: str | None = None


class AuthConfig(BaseModel):
    enabled: bool = False
    header_user: str = "Remote-User"
    header_name: str = "Remote-Name"
    header_email: str = "Remote-Email"
    header_groups: str = "Remote-Groups"
    header_group_delimiter: str = ","
    login_url: str | None = None
    logout_url: str | None = None


class NetworkClassConfig(BaseModel):
    name: str
    icon: str = "network"
    badge_color: str | None = None


class SubnetConfig(BaseModel):
    cidr: str
    name: str
    network_class: str
    icon: str | None = None

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        try:
            _ = ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR block: {v}") from e
        return v


class NetworkConfig(BaseModel):
    trusted_proxies: list[str] = Field(default_factory=lambda: ["127.0.0.1/32", "::1/128"])
    fallback_class: str = "external"
    fallback_name: str = "External / Unknown"
    fallback_icon: str = "globe"

    @field_validator("trusted_proxies")
    @classmethod
    def validate_proxies(cls, v: list[str]) -> list[str]:
        for cidr in v:
            try:
                _ = ipaddress.ip_network(cidr, strict=False)
            except ValueError as e:
                raise ValueError(f"Invalid proxy CIDR block: {cidr}") from e
        return v


class CategoryConfig(BaseModel):
    id: str
    name: str
    icon: str | None = None
    order: int = 100
    services: list[ServiceConfig] = Field(default_factory=list)


class ServiceConfig(BaseModel):
    name: str
    url: str
    description: str | None = None
    category: str
    icon: str | None = None
    fallback_icon: str | None = None
    network_classes: list[str] | None = None
    requires_groups: list[str] | None = None
    require_all_groups: bool = False
    public: bool | None = None
    target: str = "_blank"
    order: int = 100
    enabled: bool = True

    @property
    def service_id(self) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_\-]+", "-", self.name.lower()).strip("-")
        return slug or "service"

    @override
    def model_post_init(self, __context: object) -> None:
        if self.public is None:
            self.public = self.requires_groups is None or len(self.requires_groups) == 0
        if self.fallback_icon is None and self.icon is not None:
            self.fallback_icon = self.icon
        elif self.icon is None and self.fallback_icon is not None:
            self.icon = self.fallback_icon


class PortalConfig(BaseModel):
    ui: UIConfig = Field(default_factory=UIConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    network_classes: dict[str, NetworkClassConfig] = Field(default_factory=dict)
    subnets: list[SubnetConfig] = Field(default_factory=list)
    categories: list[CategoryConfig] = Field(default_factory=list)
    services: list[ServiceConfig] = Field(default_factory=list)

    def get_service_by_id(self, service_id: str) -> ServiceConfig | None:
        for s in self.services:
            if s.service_id == service_id:
                return s
        return None

    @override
    def model_post_init(self, __context: object) -> None:
        # Merge any services defined nested under categories into the main services list
        existing: dict[str, ServiceConfig] = {s.service_id: s for s in self.services}
        for cat in self.categories:
            for s in cat.services:
                if not s.category:
                    s.category = cat.id
                if s.service_id in existing:
                    target = existing[s.service_id]
                    if target.icon is None and s.icon is not None:
                        target.icon = s.icon
                    if target.fallback_icon is None and s.fallback_icon is not None:
                        target.fallback_icon = s.fallback_icon
                else:
                    self.services.append(s)
                    existing[s.service_id] = s


def find_config_file() -> Path | None:
    """Find configuration file following resolution order:
    1. PORTAL_CONFIG_PATH environment variable
    2. /etc/homelab-portal/config.yml
    3. ./config.yml in current working directory
    4. ./config.yml.example as fallback
    """
    env_path = os.environ.get("PORTAL_CONFIG_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p
        raise FileNotFoundError(f"Config file specified by PORTAL_CONFIG_PATH not found: {env_path}")

    etc_path = Path("/etc/homelab-portal/config.yml")
    if etc_path.is_file():
        return etc_path

    cwd_path = Path("config.yml")
    if cwd_path.is_file():
        return cwd_path

    example_path = Path("config.yml.example")
    if example_path.is_file():
        return example_path

    return None


def load_config(config_path: Path | str | None = None) -> PortalConfig:
    """Load and validate configuration from YAML file or return default."""
    target_path = Path(config_path) if config_path else find_config_file()
    if not target_path or not target_path.is_file():
        # Return default config if no file found
        return PortalConfig()

    with open(target_path, "r", encoding="utf-8") as f:
        data: object = yaml.safe_load(f) or {}

    return PortalConfig.model_validate(data)
