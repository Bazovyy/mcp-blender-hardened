"""Parameter validation utilities for MCP handlers."""

from typing import Any
import math


class ValidationError(Exception):
    """Raised when parameter validation fails."""

    pass


class BlenderError(Exception):
    """Raised when a Blender operation fails."""

    pass


def require_param(params: dict, name: str, param_type: type | None = None) -> Any:
    """
    Require a parameter to be present.

    Args:
        params: The parameters dict
        name: Parameter name
        param_type: Optional type to validate

    Returns:
        The parameter value

    Raises:
        ValidationError: If parameter is missing or wrong type
    """
    if name not in params:
        raise ValidationError(f"Missing required parameter: {name}")

    value = params[name]

    if param_type is not None:
        numeric_type = param_type in (int, float)
        if (numeric_type and isinstance(value, bool)) or not isinstance(value, param_type):
            raise ValidationError(
                f"Parameter '{name}' must be {param_type.__name__}, got {type(value).__name__}"
            )

    return value


def optional_param(
    params: dict,
    name: str,
    default: Any = None,
    param_type: type | None = None,
) -> Any:
    """
    Get an optional parameter with a default value.

    Args:
        params: The parameters dict
        name: Parameter name
        default: Default value if not present
        param_type: Optional type to validate

    Returns:
        The parameter value or default

    Raises:
        ValidationError: If parameter is wrong type
    """
    if name not in params:
        return default

    value = params[name]

    if param_type is not None and value is not None:
        numeric_type = param_type in (int, float)
        if (numeric_type and isinstance(value, bool)) or not isinstance(value, param_type):
            raise ValidationError(
                f"Parameter '{name}' must be {param_type.__name__}, got {type(value).__name__}"
            )

    return value


def validate_vector3(value: Any, name: str) -> list[float]:
    """
    Validate a 3D vector parameter.

    Args:
        value: The value to validate
        name: Parameter name for error messages

    Returns:
        List of 3 floats

    Raises:
        ValidationError: If not a valid vector
    """
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"Parameter '{name}' must be a list/tuple, got {type(value).__name__}")

    if len(value) != 3:
        raise ValidationError(f"Parameter '{name}' must have 3 elements, got {len(value)}")

    if any(isinstance(v, bool) for v in value):
        raise ValidationError(f"Parameter '{name}' elements must be finite numbers, not booleans")
    try:
        result = [float(v) for v in value]
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Parameter '{name}' elements must be numbers: {e}")
    if not all(math.isfinite(v) for v in result):
        raise ValidationError(f"Parameter '{name}' elements must be finite numbers")
    return result


def validate_color(value: Any, name: str) -> list[float]:
    """
    Validate an RGBA color parameter.

    Args:
        value: The value to validate
        name: Parameter name for error messages

    Returns:
        List of 3 or 4 floats (RGB or RGBA)

    Raises:
        ValidationError: If not a valid color
    """
    if not isinstance(value, (list, tuple)):
        raise ValidationError(f"Parameter '{name}' must be a list/tuple, got {type(value).__name__}")

    if len(value) not in (3, 4):
        raise ValidationError(f"Parameter '{name}' must have 3 or 4 elements (RGB/RGBA)")

    if any(isinstance(v, bool) for v in value):
        raise ValidationError(f"Parameter '{name}' elements must be finite numbers, not booleans")
    try:
        color = [float(v) for v in value]
    except (TypeError, ValueError) as e:
        raise ValidationError(f"Parameter '{name}' elements must be numbers: {e}")
    if not all(math.isfinite(v) for v in color):
        raise ValidationError(f"Parameter '{name}' elements must be finite numbers")

    # Pad to 4 elements if RGB
    if len(color) == 3:
        color.append(1.0)

    # Validate range
    for i, v in enumerate(color):
        if not 0.0 <= v <= 1.0:
            raise ValidationError(
                f"Parameter '{name}' values must be 0-1, got {v} at index {i}"
            )

    return color


def validate_enum(value: Any, name: str, allowed: list[str]) -> str:
    """
    Validate an enum parameter.

    Args:
        value: The value to validate
        name: Parameter name for error messages
        allowed: List of allowed values

    Returns:
        The validated value (uppercased)

    Raises:
        ValidationError: If not a valid enum value
    """
    if not isinstance(value, str):
        raise ValidationError(f"Parameter '{name}' must be a string")

    upper_value = value.upper()
    upper_allowed = [a.upper() for a in allowed]

    if upper_value not in upper_allowed:
        raise ValidationError(
            f"Parameter '{name}' must be one of {allowed}, got '{value}'"
        )

    return upper_value


def validate_filepath(value: Any, name: str, must_exist: bool = False) -> str:
    """
    Validate a file path parameter.

    Args:
        value: The value to validate
        name: Parameter name for error messages
        must_exist: Whether the file must exist

    Returns:
        The validated path

    Raises:
        ValidationError: If not a valid path
    """
    import os

    if not isinstance(value, str):
        raise ValidationError(f"Parameter '{name}' must be a string")

    if not value.strip():
        raise ValidationError(f"Parameter '{name}' cannot be empty")

    if must_exist and not os.path.exists(value):
        raise ValidationError(f"File not found: {value}")

    return value


def require_any_param(params: dict, names: list[str] | tuple[str, ...]) -> str:
    """Require at least one named parameter to contain a meaningful value."""
    for name in names:
        if name not in params:
            continue
        value = params[name]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return name
    joined = ", ".join(names)
    raise ValidationError(f"At least one of these parameters is required: {joined}")
