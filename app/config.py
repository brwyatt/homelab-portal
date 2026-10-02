"""Configuration loader and schema models for Homelab Portal."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional
import ipaddress
import yaml
from pydantic import BaseModel, Field, field_validator


class UIConfig(BaseModel):
    title: str = "Homelab Portal"
    subtitle: Optional[str] = "Services & Resources"
    theme: str = "fiber-optic"
    custom_themes_dir: Optional[str] = None
    show_search: bool = True
    show_network_badge: bool = True
    show_user_badge: bool = True
    footer_text: Optional[str] = None


class AuthConfig(BaseModel):
    enabled: bool = False
    header_user: str = "Remote-User"
    header_name: str = "Remote-Name"
    header_email: str = "Remote-Email"
    header_groups: str = "Remote-Groups"
    header_group_delimiter: str = ","
    login_url: Optional[str] = None
    logout_url: Optional[str] = None


class NetworkClassConfig(BaseModel):
    name: str
    icon: str = "network"
    badge_color: Optional[str] = None


class SubnetConfig(BaseModel):
    cidr: str
    name: str
    network_class: str
    icon: Optional[str] = None

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        try:
            ipaddress.ip_network(v, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR block: {v}") from e
        return v


class NetworkConfig(BaseModel):
    trusted_proxies: List[str] = Field(default_factory=lambda: ["127.0.0.1/32", "::1/128"])
    fallback_class: str = "external"
    fallback_name: str = "External / Unknown"
    fallback_icon: str = "globe"

    @field_validator("trusted_proxies")
    @classmethod
    def validate_proxies(cls, v: List[str]) -> List[str]:
        for cidr in v:
            try:
                ipaddress.ip_network(cidr, strict=False)
            except ValueError as e:
                raise ValueError(f"Invalid proxy CIDR block: {cidr}") from e
        return v


class CategoryConfig(BaseModel):
    id: str
    name: str
    icon: Optional[str] = None
    order: int = 100


class ServiceConfig(BaseModel):
    name: str
    url: str
    description: Optional[str] = None
    category: str
    icon: Optional[str] = None
    network_classes: Optional[List[str]] = None
    requires_groups: Optional[List[str]] = None
    require_all_groups: bool = False
    public: Optional[bool] = None
    target: str = "_blank"
    order: int = 100
    enabled: bool = True

    def model_post_init(self, __context: object) -> None:
        if self.public is None:
            self.public = self.requires_groups is None or len(self.requires_groups) == 0


class PortalConfig(BaseModel):
    ui: UIConfig = Field(default_factory=UIConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    network_classes: Dict[str, NetworkClassConfig] = Field(default_factory=dict)
    subnets: List[SubnetConfig] = Field(default_factory=list)
    categories: List[CategoryConfig] = Field(default_factory=list)
    services: List[ServiceConfig] = Field(default_factory=list)


def find_config_file() -> Optional[Path]:
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


def load_config(config_path: Optional[Path | str] = None) -> PortalConfig:
    """Load and validate configuration from YAML file or return default."""
    target_path = Path(config_path) if config_path else find_config_file()
    if not target_path or not target_path.is_file():
        # Return default config if no file found
        return PortalConfig()

    with open(target_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return PortalConfig.model_validate(data)
