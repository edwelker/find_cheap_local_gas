from pydantic import BaseModel, Field, computed_field, RootModel
from typing import Optional, Dict


class Coordinates(BaseModel):
    """Simple lat/long structure."""

    lat: Optional[float]
    lon: Optional[float]


class GeocodeCache(RootModel):
    """Model for the geocache.json file."""

    root: Dict[str, Coordinates]


class GasStation(BaseModel):
    """
    Data model for a Gas Station result.
    Handles validation and automatic net price calculation.
    """

    city: str = Field(alias="City")
    zip_code: str = Field(alias="Zip")
    station_name: str = Field(alias="Station")
    address: str = Field(alias="Address")
    base_price: float = Field(alias="Base")
    discount_rule: str = Field(alias="Discount", default="-")
    discount_amount: float = Field(default=0.0, exclude=True)
    street_name: Optional[str] = Field(alias="Street", default=None, exclude=True)

    # Geocoding fields (populated later)
    lat: Optional[float] = Field(alias="Lat", default=None)
    long: Optional[float] = Field(alias="Long", default=None)

    @computed_field(alias="Net")
    @property
    def net_price(self) -> float:
        """Automatically calculates net price after discount."""
        return round(self.base_price - self.discount_amount, 2)

    class Config:
        populate_by_name = True
        serialize_by_alias = True
