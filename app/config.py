"""Configuration loader and validator for PLC Self-Healing Middleware."""
import os
import re
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class PLCConfig:
    """PLC connection configuration."""
    ip_address: str
    slot: int = 0
    timeout: float = 5.0
    poll_interval_ms: int = 1000
    mock_mode: bool = False  # Enable mock mode for graceful handling of unsupported services
    protocol_mode: str = "default"  # Protocol mode: "default" (use pycomm3 default) or "serial" (disable MSP, use serial methods)


@dataclass
class TagConfig:
    """Tag monitoring configuration."""
    name: str
    type: str  # bool, int, float
    nominal: Any
    failure_condition: str  # equals, not_equals, outside_range, below, above
    failure_value: Optional[Any] = None
    failure_threshold_low: Optional[float] = None
    failure_threshold_high: Optional[float] = None


@dataclass
class AAPConfig:
    """Ansible Automation Platform configuration."""
    enabled: bool = True
    mock_mode: bool = True
    base_url: str = ""
    verify_ssl: bool = True
    token: str = ""
    job_templates: Dict[str, int] = field(default_factory=dict)


@dataclass
class RemediationConfig:
    """Remediation configuration."""
    auto_remediate: bool = False
    cooldown_seconds: int = 30
    max_retries: int = 3


@dataclass
class ChaosConfig:
    """Chaos engineering configuration."""
    enabled: bool = False
    failure_injection_rate: float = 0.05
    failure_types: List[str] = field(default_factory=lambda: [
        "value_anomaly", "network_timeout", "connection_loss", "service_crash"
    ])
    network_timeout_ms: int = 5000
    anomaly_duration_seconds: int = 10


@dataclass
class DashboardConfig:
    """Dashboard configuration."""
    refresh_interval_ms: int = 1000
    history_retention_hours: int = 24
    chart_data_points: int = 100


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class AppConfig:
    """Application configuration container."""
    plc: PLCConfig
    tags: Dict[str, TagConfig]
    aap: AAPConfig
    remediation: RemediationConfig
    chaos: ChaosConfig
    dashboard: DashboardConfig
    logging: LoggingConfig


class ConfigLoader:
    """Load and validate configuration from YAML file."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize config loader.
        
        Args:
            config_path: Path to config.yaml file. If None, looks for config/config.yaml
        """
        if config_path is None:
            # Default to config/config.yaml relative to project root
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config" / "config.yaml"
        
        self.config_path = Path(config_path)
        self._config: Optional[AppConfig] = None
    
    def _substitute_env_vars(self, text: str) -> str:
        """Substitute environment variables in format ${VAR_NAME}.
        
        Args:
            text: String potentially containing ${VAR_NAME} patterns
            
        Returns:
            String with environment variables substituted
        """
        def replace_var(match):
            var_name = match.group(1)
            return os.getenv(var_name, match.group(0))  # Return original if not found
        
        pattern = r'\$\{([^}]+)\}'
        return re.sub(pattern, replace_var, text)
    
    def _substitute_in_dict(self, data: Any) -> Any:
        """Recursively substitute environment variables in dict/list/str values.
        
        Args:
            data: Data structure (dict, list, str, or other)
            
        Returns:
            Data structure with environment variables substituted
        """
        if isinstance(data, dict):
            return {k: self._substitute_in_dict(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._substitute_in_dict(item) for item in data]
        elif isinstance(data, str):
            return self._substitute_env_vars(data)
        else:
            return data
    
    def _load_yaml(self) -> Dict[str, Any]:
        """Load YAML file and substitute environment variables.
        
        Returns:
            Parsed YAML as dictionary
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML is invalid
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            raw_data = yaml.safe_load(f)
        
        if raw_data is None:
            raise ValueError("Configuration file is empty")
        
        # Substitute environment variables
        return self._substitute_in_dict(raw_data)
    
    def _validate_plc_config(self, plc_data: Dict[str, Any]) -> PLCConfig:
        """Validate and create PLCConfig.
        
        Args:
            plc_data: PLC configuration dictionary
            
        Returns:
            Validated PLCConfig instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        if 'ip_address' not in plc_data:
            raise ValueError("PLC configuration missing required field: ip_address")
        
        # Validate protocol_mode
        protocol_mode = str(plc_data.get('protocol_mode', 'default')).lower()
        if protocol_mode not in ['default', 'serial']:
            raise ValueError(
                f"Invalid protocol_mode '{protocol_mode}'. Must be 'default' or 'serial'"
            )
        
        return PLCConfig(
            ip_address=str(plc_data['ip_address']),
            slot=int(plc_data.get('slot', 0)),
            timeout=float(plc_data.get('timeout', 5.0)),
            poll_interval_ms=int(plc_data.get('poll_interval_ms', 1000)),
            mock_mode=bool(plc_data.get('mock_mode', False)),
            protocol_mode=protocol_mode
        )
    
    def _validate_tag_config(self, tag_name: str, tag_data: Dict[str, Any]) -> TagConfig:
        """Validate and create TagConfig.
        
        Args:
            tag_name: Key name for the tag
            tag_data: Tag configuration dictionary
            
        Returns:
            Validated TagConfig instance
            
        Raises:
            ValueError: If required fields are missing or invalid
        """
        required_fields = ['name', 'type', 'nominal', 'failure_condition']
        for field in required_fields:
            if field not in tag_data:
                raise ValueError(f"Tag '{tag_name}' missing required field: {field}")
        
        failure_condition = tag_data['failure_condition']
        
        # Validate failure_condition-specific fields
        if failure_condition in ['equals', 'not_equals']:
            if 'failure_value' not in tag_data:
                raise ValueError(
                    f"Tag '{tag_name}' with condition '{failure_condition}' "
                    "requires 'failure_value' field"
                )
        elif failure_condition == 'outside_range':
            if 'failure_threshold_low' not in tag_data or 'failure_threshold_high' not in tag_data:
                raise ValueError(
                    f"Tag '{tag_name}' with condition 'outside_range' "
                    "requires 'failure_threshold_low' and 'failure_threshold_high' fields"
                )
        elif failure_condition in ['below', 'above']:
            threshold_key = f"failure_threshold_{failure_condition}"
            if threshold_key not in tag_data:
                raise ValueError(
                    f"Tag '{tag_name}' with condition '{failure_condition}' "
                    f"requires '{threshold_key}' field"
                )
        
        return TagConfig(
            name=str(tag_data['name']),
            type=str(tag_data['type']),
            nominal=tag_data['nominal'],
            failure_condition=str(tag_data['failure_condition']),
            failure_value=tag_data.get('failure_value'),
            failure_threshold_low=tag_data.get('failure_threshold_low'),
            failure_threshold_high=tag_data.get('failure_threshold_high')
        )
    
    def _validate_aap_config(self, aap_data: Dict[str, Any]) -> AAPConfig:
        """Validate and create AAPConfig.
        
        Args:
            aap_data: AAP configuration dictionary
            
        Returns:
            Validated AAPConfig instance
        """
        return AAPConfig(
            enabled=bool(aap_data.get('enabled', True)),
            mock_mode=bool(aap_data.get('mock_mode', True)),
            base_url=str(aap_data.get('base_url', '')),
            verify_ssl=bool(aap_data.get('verify_ssl', True)),
            token=str(aap_data.get('token', '')),
            job_templates=dict(aap_data.get('job_templates', {}))
        )
    
    def _validate_remediation_config(self, remediation_data: Dict[str, Any]) -> RemediationConfig:
        """Validate and create RemediationConfig.
        
        Args:
            remediation_data: Remediation configuration dictionary
            
        Returns:
            Validated RemediationConfig instance
        """
        return RemediationConfig(
            auto_remediate=bool(remediation_data.get('auto_remediate', False)),
            cooldown_seconds=int(remediation_data.get('cooldown_seconds', 30)),
            max_retries=int(remediation_data.get('max_retries', 3))
        )
    
    def _validate_chaos_config(self, chaos_data: Dict[str, Any]) -> ChaosConfig:
        """Validate and create ChaosConfig.
        
        Args:
            chaos_data: Chaos configuration dictionary
            
        Returns:
            Validated ChaosConfig instance
        """
        return ChaosConfig(
            enabled=bool(chaos_data.get('enabled', False)),
            failure_injection_rate=float(chaos_data.get('failure_injection_rate', 0.05)),
            failure_types=list(chaos_data.get('failure_types', [
                "value_anomaly", "network_timeout", "connection_loss", "service_crash"
            ])),
            network_timeout_ms=int(chaos_data.get('network_timeout_ms', 5000)),
            anomaly_duration_seconds=int(chaos_data.get('anomaly_duration_seconds', 10))
        )
    
    def _validate_dashboard_config(self, dashboard_data: Dict[str, Any]) -> DashboardConfig:
        """Validate and create DashboardConfig.
        
        Args:
            dashboard_data: Dashboard configuration dictionary
            
        Returns:
            Validated DashboardConfig instance
        """
        return DashboardConfig(
            refresh_interval_ms=int(dashboard_data.get('refresh_interval_ms', 1000)),
            history_retention_hours=int(dashboard_data.get('history_retention_hours', 24)),
            chart_data_points=int(dashboard_data.get('chart_data_points', 100))
        )
    
    def _validate_logging_config(self, logging_data: Dict[str, Any]) -> LoggingConfig:
        """Validate and create LoggingConfig.
        
        Args:
            logging_data: Logging configuration dictionary
            
        Returns:
            Validated LoggingConfig instance
            
        Raises:
            ValueError: If log level is invalid
        """
        level = str(logging_data.get('level', 'INFO')).upper()
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        
        if level not in valid_levels:
            raise ValueError(
                f"Invalid log level '{level}'. Must be one of: {', '.join(valid_levels)}"
            )
        
        log_format = str(logging_data.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        
        return LoggingConfig(
            level=level,
            format=log_format
        )
    
    def load(self) -> AppConfig:
        """Load and validate configuration.
        
        Returns:
            Validated AppConfig instance
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If configuration is invalid
        """
        data = self._load_yaml()
        
        # Validate required sections
        if 'plc' not in data:
            raise ValueError("Configuration missing required section: plc")
        if 'tags' not in data:
            raise ValueError("Configuration missing required section: tags")
        if not data['tags']:
            raise ValueError("Configuration must define at least one tag")
        
        # Build configuration objects
        plc_config = self._validate_plc_config(data['plc'])
        
        tags_config = {}
        for tag_name, tag_data in data['tags'].items():
            tags_config[tag_name] = self._validate_tag_config(tag_name, tag_data)
        
        aap_config = self._validate_aap_config(data.get('aap', {}))
        remediation_config = self._validate_remediation_config(data.get('remediation', {}))
        chaos_config = self._validate_chaos_config(data.get('chaos', {}))
        dashboard_config = self._validate_dashboard_config(data.get('dashboard', {}))
        logging_config = self._validate_logging_config(data.get('logging', {}))
        
        self._config = AppConfig(
            plc=plc_config,
            tags=tags_config,
            aap=aap_config,
            remediation=remediation_config,
            chaos=chaos_config,
            dashboard=dashboard_config,
            logging=logging_config
        )
        
        return self._config
    
    def get_config(self) -> AppConfig:
        """Get loaded configuration.
        
        Returns:
            AppConfig instance
            
        Raises:
            RuntimeError: If configuration hasn't been loaded yet
        """
        if self._config is None:
            raise RuntimeError("Configuration not loaded. Call load() first.")
        return self._config


# Global config loader instance
_config_loader: Optional[ConfigLoader] = None


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from file.
    
    Args:
        config_path: Path to config.yaml. If None, uses default location.
        
    Returns:
        AppConfig instance
    """
    global _config_loader
    _config_loader = ConfigLoader(config_path)
    return _config_loader.load()


def get_config() -> AppConfig:
    """Get the loaded configuration.
    
    Returns:
        AppConfig instance
        
    Raises:
        RuntimeError: If configuration hasn't been loaded
    """
    if _config_loader is None:
        raise RuntimeError("Configuration not loaded. Call load_config() first.")
    return _config_loader.get_config()
