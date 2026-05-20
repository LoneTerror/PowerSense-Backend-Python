class PowerSenseException(Exception):
    """Base exception for all custom PowerSense errors."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class HardwareOfflineException(PowerSenseException):
    def __init__(self, message="Hardware device (ESP8266) is offline"):
        super().__init__(message=message, status_code=503)

class ResourceNotFoundException(PowerSenseException):
    def __init__(self, resource_name: str, resource_id: int):
        super().__init__(message=f"{resource_name} with ID {resource_id} not found", status_code=404)