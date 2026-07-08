"""Exceptions for MikroTik WiFi Approval."""

from __future__ import annotations


class MikrotikWifiApprovalError(Exception):
    """Base exception for the integration."""


class CannotConnect(MikrotikWifiApprovalError):
    """Unable to connect to MikroTik."""


class InvalidAuth(MikrotikWifiApprovalError):
    """Authentication failed."""


class ApiError(MikrotikWifiApprovalError):
    """RouterOS returned an API error."""