from __future__ import annotations


class BloodGroup:
    """
    Canonical blood group values used across the platform.
    Stored as short strings for portability.
    """

    O_POS = "O+"
    O_NEG = "O-"
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"

    CHOICES = (
        (O_POS, "O+"),
        (O_NEG, "O-"),
        (A_POS, "A+"),
        (A_NEG, "A-"),
        (B_POS, "B+"),
        (B_NEG, "B-"),
        (AB_POS, "AB+"),
        (AB_NEG, "AB-"),
    )


