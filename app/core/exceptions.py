from fastapi import HTTPException, status


def service_not_found(service_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Service '{service_name}' was not found",
    )


def version_not_found(service_name: str, version: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Version {version} for service '{service_name}' was not found",
    )


def duplicate_service(service_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Service '{service_name}' already exists",
    )


def active_version_delete_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Cannot delete the active config version",
    )
