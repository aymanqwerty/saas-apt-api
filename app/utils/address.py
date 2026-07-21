from app.models.clinic import Clinic


def compose_clinic_address(clinic: Clinic) -> str:
    parts = [clinic.address_line_1]
    if clinic.address_line_2:
        parts.append(clinic.address_line_2)
    parts.extend([clinic.city, clinic.state, clinic.country])
    if clinic.postal_code:
        parts.append(clinic.postal_code)
    return ", ".join(parts)
