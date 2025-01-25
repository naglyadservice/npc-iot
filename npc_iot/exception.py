class DeviceResponceError(Exception):
    def __init__(self, code: int):
        self.code = code
        super().__init__(f"Error code {code} in response from device")
