"""Tag management with operating mode support for CIP PLC simulator."""
import time
import random
import logging
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class OperatingMode(Enum):
    """PLC operating modes."""
    NORMAL = "normal"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNRESPONSIVE = "unresponsive"


class TagManager:
    """Manages PLC tags with operating mode support."""
    
    # Default tag values matching config.yaml structure
    DEFAULT_TAGS = {
        "Light_Status": {
            "type": "BOOL",
            "value": True,
            "nominal": True,
            "failure_value": False
        },
        "Motor_Speed": {
            "type": "DINT",
            "value": 1750,
            "nominal": 1750,
            "variance": 50,
            "failure_threshold_low": 1500,
            "failure_threshold_high": 2000
        },
        "Motor_Direction": {
            "type": "DINT",
            "value": 1,
            "nominal": 1
        },
        "Motor_Run": {
            "type": "BOOL",
            "value": True,
            "nominal": True
        }
    }
    
    # CIP data type mappings
    CIP_TYPE_MAP = {
        "bool": "BOOL",
        "int": "DINT",
        "float": "REAL",
        "string": "STRING"
    }
    
    def __init__(self, mode: OperatingMode = OperatingMode.NORMAL):
        """Initialize tag manager.
        
        Args:
            mode: Initial operating mode
        """
        self.mode = mode
        self.tags: Dict[str, Dict[str, Any]] = {}
        
        # Initialize tags from defaults
        for tag_name, tag_data in self.DEFAULT_TAGS.items():
            self.tags[tag_name] = tag_data.copy()
        
        # Degradation state
        self.degradation_start = time.time()
        self.degradation_progress = 0.0
        
        # Tag access statistics
        self.read_count = 0
        self.write_count = 0
    
    def set_mode(self, mode: OperatingMode):
        """Change operating mode.
        
        Args:
            mode: New operating mode
        """
        self.mode = mode
        self.degradation_start = time.time()
        self.degradation_progress = 0.0
        logger.info(f"Tag manager mode changed to {mode.value}")
    
    def get_tag_value(self, tag_name: str) -> Any:
        """Get current tag value based on operating mode.
        
        Args:
            tag_name: Name of the tag
            
        Returns:
            Current tag value (transformed by mode)
            
        Raises:
            KeyError: If tag doesn't exist
        """
        if tag_name not in self.tags:
            raise KeyError(f"Tag {tag_name} not found")
        
        tag_data = self.tags[tag_name]
        base_value = tag_data["value"]
        tag_type = tag_data.get("type", "DINT")
        nominal = tag_data.get("nominal", base_value)
        
        self.read_count += 1
        
        if self.mode == OperatingMode.NORMAL:
            return self._get_normal_value(tag_data, tag_type, nominal, base_value)
        elif self.mode == OperatingMode.DEGRADED:
            return self._get_degraded_value(tag_data, tag_type, nominal, base_value)
        elif self.mode == OperatingMode.FAILED:
            return self._get_failed_value(tag_data, tag_type, nominal, base_value)
        else:  # UNRESPONSIVE
            return base_value  # Won't be sent anyway
    
    def _get_normal_value(self, tag_data: Dict, tag_type: str, nominal: Any, base_value: Any) -> Any:
        """Get value in normal mode (with small variance)."""
        if tag_type == "BOOL":
            return nominal
        elif tag_type in ["INT", "DINT"]:
            if "variance" in tag_data:
                variance = tag_data["variance"]
                return int(nominal + random.randint(-variance, variance))
            return int(nominal)
        elif tag_type == "REAL":
            if "variance" in tag_data:
                variance = tag_data["variance"]
                return float(nominal + random.uniform(-variance, variance))
            return float(nominal)
        else:
            return nominal
    
    def _get_degraded_value(self, tag_data: Dict, tag_type: str, nominal: Any, base_value: Any) -> Any:
        """Get value in degraded mode (gradual drift toward failure)."""
        # Calculate degradation progress (0.0 to 1.0)
        elapsed = time.time() - self.degradation_start
        self.degradation_progress = min(1.0, elapsed / 60.0)  # Full degradation in 60 seconds
        
        if tag_type in ["INT", "DINT"]:
            # Drift toward failure threshold
            if "failure_threshold_low" in tag_data:
                target = tag_data["failure_threshold_low"] - 10
                return int(nominal + (target - nominal) * self.degradation_progress)
            elif "failure_threshold_high" in tag_data:
                target = tag_data["failure_threshold_high"] + 10
                return int(nominal + (target - nominal) * self.degradation_progress)
            else:
                return int(nominal * (1.0 - self.degradation_progress * 0.3))
        elif tag_type == "BOOL":
            # Eventually flip to failure value
            if self.degradation_progress > 0.8:
                return tag_data.get("failure_value", not nominal)
            return nominal
        elif tag_type == "REAL":
            # Similar to INT
            if "failure_threshold_low" in tag_data:
                target = tag_data["failure_threshold_low"] - 10.0
                return float(nominal + (target - nominal) * self.degradation_progress)
            elif "failure_threshold_high" in tag_data:
                target = tag_data["failure_threshold_high"] + 10.0
                return float(nominal + (target - nominal) * self.degradation_progress)
            else:
                return float(nominal * (1.0 - self.degradation_progress * 0.3))
        else:
            return base_value
    
    def _get_failed_value(self, tag_data: Dict, tag_type: str, nominal: Any, base_value: Any) -> Any:
        """Get value in failed mode (failure condition values)."""
        if tag_type == "BOOL":
            return tag_data.get("failure_value", not nominal)
        elif tag_type in ["INT", "DINT"]:
            # Return value outside normal range
            if "failure_threshold_low" in tag_data:
                return int(tag_data["failure_threshold_low"] - 100)
            elif "failure_threshold_high" in tag_data:
                return int(tag_data["failure_threshold_high"] + 100)
            else:
                return 0  # Default failure value
        elif tag_type == "REAL":
            if "failure_threshold_low" in tag_data:
                return float(tag_data["failure_threshold_low"] - 100.0)
            elif "failure_threshold_high" in tag_data:
                return float(tag_data["failure_threshold_high"] + 100.0)
            else:
                return 0.0
        else:
            return base_value
    
    def set_tag_value(self, tag_name: str, value: Any) -> bool:
        """Set tag value (updates base value, mode transformation still applies on read).
        
        Args:
            tag_name: Name of the tag
            value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        if tag_name not in self.tags:
            logger.warning(f"Attempted to write non-existent tag: {tag_name}")
            return False
        
        tag_data = self.tags[tag_name]
        
        # Validate type
        tag_type = tag_data.get("type", "DINT")
        try:
            if tag_type == "BOOL":
                tag_data["value"] = bool(value)
            elif tag_type in ["INT", "DINT"]:
                tag_data["value"] = int(value)
            elif tag_type == "REAL":
                tag_data["value"] = float(value)
            else:
                tag_data["value"] = value
            
            self.write_count += 1
            logger.debug(f"Tag {tag_name} set to {tag_data['value']}")
            return True
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to set tag {tag_name}: {e}")
            return False
    
    def get_tag_info(self, tag_name: str) -> Optional[Dict[str, Any]]:
        """Get tag information (type, dimensions, etc.).
        
        Args:
            tag_name: Name of the tag
            
        Returns:
            Tag information dictionary or None if not found
        """
        if tag_name not in self.tags:
            return None
        
        tag_data = self.tags[tag_name]
        return {
            "name": tag_name,
            "type": tag_data.get("type", "DINT"),
            "nominal": tag_data.get("nominal"),
            "current_value": self.get_tag_value(tag_name)
        }
    
    def list_tags(self) -> list:
        """List all available tag names.
        
        Returns:
            List of tag names
        """
        return list(self.tags.keys())
    
    def add_tag(self, tag_name: str, tag_type: str, initial_value: Any, **kwargs):
        """Add a new tag.
        
        Args:
            tag_name: Name of the tag
            tag_type: CIP data type (BOOL, DINT, REAL, etc.)
            initial_value: Initial value
            **kwargs: Additional tag properties (nominal, variance, etc.)
        """
        self.tags[tag_name] = {
            "type": tag_type,
            "value": initial_value,
            "nominal": kwargs.get("nominal", initial_value),
            **kwargs
        }
        logger.info(f"Added tag {tag_name} of type {tag_type}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tag access statistics.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "total_tags": len(self.tags),
            "read_count": self.read_count,
            "write_count": self.write_count,
            "mode": self.mode.value,
            "degradation_progress": self.degradation_progress
        }
