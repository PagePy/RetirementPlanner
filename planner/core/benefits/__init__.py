"""Prestations gouvernementales: RRQ/CPP, SV (OAS), SRG (GIS) et Allocation."""

from planner.core.benefits.rrq import RRQ
from planner.core.benefits.oas import OAS
from planner.core.benefits.gis import GIS

__all__ = ["RRQ", "OAS", "GIS"]
