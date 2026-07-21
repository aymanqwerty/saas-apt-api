from pydantic import BaseModel


class ApiResponse[T](BaseModel):
    success: bool = True
    message: str = "Success"
    data: T
