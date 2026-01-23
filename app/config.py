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
        """Substitute environment variables in format ${VAR_NAME} or ${VAR_NAME:-default}.
        
        Supports shell-style default values: ${VAR_NAME:-default_value}
        If the environment variable is not set, the default value is used.
        
        Args:
            text: String potentially containing ${VAR_NAME} or ${VAR_NAME:-default} patterns
            
        Returns:
            String with environment variables substituted
        """
        def replace_var(match):
            var_expr = match.group(1)  # e.g., "VAR_NAME" or "VAR_NAME:-default"
            
            # Check if default value is specified
            if ':-' in var_expr:
                var_name, default_value = var_expr.split(':-', 1)
                var_name = var_name.strip()
                default_value = default_value.strip()
                return os.getenv(var_name, default_value)
            else:
                var_name = var_expr.strip()
                env_value = os.getenv(var_name)
                if env_value is not None:
                    return env_value
                # Return original pattern if not found (for backward compatibility)
                return match.group(0)
        
        pattern = r'\$\{([^}]+)\}'
        return re.sub(pattern, replace_var, text)
    
    def _convert_value_type(self, value: Any) -> Any:
        """Convert string value to appropriate type based on context.
        
        Handles conversion of environment variable strings to:
        - Boolean: "true"/"True"/"TRUE"/"1" -> True, "false"/"False"/"FALSE"/"0"/"" -> False
        - Integer: numeric strings -> int
        - Float: numeric strings with decimal -> float
        - List: comma-separated strings -> list
        
        Args:
            value: Value to convert (usually a string from env var)
            
        Returns:
            Converted value with appropriate type
        """
        if not isinstance(value, str):
            return value
        
        value = value.strip()
        
        # Try boolean conversion first (common case)
        if value.lower() in ('true', '1', 'yes', 'on'):
            return True
        if value.lower() in ('false', '0', 'no', 'off', ''):
            return False
        
        # Try integer conversion (only if no decimal point)
        if '.' not in value:
            try:
                return int(value)
            except ValueError:
                pass
        
        # Try float conversion
        try:
            return float(value)
        except ValueError:
            pass
        
        # Try list conversion (comma-separated)
        if ',' in value:
            return [item.strip() for item in value.split(',') if item.strip()]
        
        # Return as string if no conversion applies
        return value
    
    def _substitute_in_dict(self, data: Any) -> Any:
        """Recursively substitute environment variables in dict/list/str values.
        
        After substitution, attempts type conversion for common cases.
        
        Args:
            data: Data structure (dict, list, str, or other)
            
        Returns:
            Data structure with environment variables substituted and types converted
        """
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                substituted = self._substitute_in_dict(v)
                # Convert value if it's a string that looks like a boolean/number/list
                if isinstance(substituted, str):
                    converted = self._convert_value_type(substituted)
                    result[k] = converted
                else:
                    result[k] = substituted
            return result
        elif isinstance(data, list):
            return [self._substitute_in_dict(item) for item in data]
        elif isinstance(data, str):
            substituted = self._substitute_env_vars(data)
            # Convert if substitution occurred or if it's a simple value that needs conversion
            converted = self._convert_value_type(substituted)
            return converted
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
        
        # Values should already be converted by _substitute_in_dict, but ensure proper types
        slot_val = plc_data.get('slot', 0)
        timeout_val = plc_data.get('timeout', 5.0)
        poll_interval_val = plc_data.get('poll_interval_ms', 1000)
        mock_mode_val = plc_data.get('mock_mode', False)
        
        return PLCConfig(
            ip_address=str(plc_data['ip_address']),
            slot=int(slot_val) if not isinstance(slot_val, (int, bool)) else slot_val,
            timeout=float(timeout_val) if not isinstance(timeout_val, (float, int)) else float(timeout_val),
            poll_interval_ms=int(poll_interval_val) if not isinstance(poll_interval_val, int) else poll_interval_val,
            mock_mode=bool(mock_mode_val) if not isinstance(mock_mode_val, bool) else mock_mode_val,
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
        # Convert job templates values to int
        job_templates = {}
        for key, value in aap_data.get('job_templates', {}).items():
            job_templates[key] = int(value) if not isinstance(value, int) else value
        
        enabled_val = aap_data.get('enabled', True)
        mock_mode_val = aap_data.get('mock_mode', True)
        verify_ssl_val = aap_data.get('verify_ssl', True)
        
        return AAPConfig(
            enabled=bool(enabled_val) if not isinstance(enabled_val, bool) else enabled_val,
            mock_mode=bool(mock_mode_val) if not isinstance(mock_mode_val, bool) else mock_mode_val,
            base_url=str(aap_data.get('base_url', '')),
            verify_ssl=bool(verify_ssl_val) if not isinstance(verify_ssl_val, bool) else verify_ssl_val,
            token=str(aap_data.get('token', '')),
            job_templates=job_templates
        )
    
    def _validate_remediation_config(self, remediation_data: Dict[str, Any]) -> RemediationConfig:
        """Validate and create RemediationConfig.
        
        Args:
            remediation_data: Remediation configuration dictionary
            
        Returns:
            Validated RemediationConfig instance
        """
        auto_remediate_val = remediation_data.get('auto_remediate', False)
        cooldown_val = remediation_data.get('cooldown_seconds', 30)
        max_retries_val = remediation_data.get('max_retries', 3)
        
        return RemediationConfig(
            auto_remediate=bool(auto_remediate_val) if not isinstance(auto_remediate_val, bool) else auto_remediate_val,
            cooldown_seconds=int(cooldown_val) if not isinstance(cooldown_val, int) else cooldown_val,
            max_retries=int(max_retries_val) if not isinstance(max_retries_val, int) else max_retries_val
        )
    
    def _validate_chaos_config(self, chaos_data: Dict[str, Any]) -> ChaosConfig:
        """Validate and create ChaosConfig.
        
        Args:
            chaos_data: Chaos configuration dictionary
            
        Returns:
            Validated ChaosConfig instance
        """
        enabled_val = chaos_data.get('enabled', False)
        failure_injection_rate_val = chaos_data.get('failure_injection_rate', 0.05)
        failure_types_val = chaos_data.get('failure_types', [
            "value_anomaly", "network_timeout", "connection_loss", "service_crash"
        ])
        network_timeout_val = chaos_data.get('network_timeout_ms', 5000)
        anomaly_duration_val = chaos_data.get('anomaly_duration_seconds', 10)
        
        # Handle failure_types - could be a list or comma-separated string (already converted by _substitute_in_dict)
        if isinstance(failure_types_val, list):
            failure_types_list = failure_types_val
        else:
            # Fallback for non-list values
            failure_types_list = [
                "value_anomaly", "network_timeout", "connection_loss", "service_crash"
            ]
        
        return ChaosConfig(
            enabled=bool(enabled_val) if not isinstance(enabled_val, bool) else enabled_val,
            failure_injection_rate=float(failure_injection_rate_val) if not isinstance(failure_injection_rate_val, (float, int)) else float(failure_injection_rate_val),
            failure_types=failure_types_list,
            network_timeout_ms=int(network_timeout_val) if not isinstance(network_timeout_val, int) else network_timeout_val,
            anomaly_duration_seconds=int(anomaly_duration_val) if not isinstance(anomaly_duration_val, int) else anomaly_duration_val
        )
    
    def _validate_dashboard_config(self, dashboard_data: Dict[str, Any]) -> DashboardConfig:
        """Validate and create DashboardConfig.
        
        Args:
            dashboard_data: Dashboard configuration dictionary
            
        Returns:
            Validated DashboardConfig instance
        """
        refresh_interval_val = dashboard_data.get('refresh_interval_ms', 1000)
        history_retention_val = dashboard_data.get('history_retention_hours', 24)
        chart_data_points_val = dashboard_data.get('chart_data_points', 100)
        
        return DashboardConfig(
            refresh_interval_ms=int(refresh_interval_val) if not isinstance(refresh_interval_val, int) else refresh_interval_val,
            history_retention_hours=int(history_retention_val) if not isinstance(history_retention_val, int) else history_retention_val,
            chart_data_points=int(chart_data_points_val) if not isinstance(chart_data_points_val, int) else chart_data_points_val
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
