"""Validate reproducible, virtual-time simulation experiment settings."""

from pydantic import BaseModel, ConfigDict, Field


class SimulationConfiguration(BaseModel):
    """Configure independent replications in seconds of *virtual* time.

    This nested model is read through the root Pydantic AppSettings object;
    environment variables use ASD_SIMULATION__FIELD_NAME. Neither virtual
    time nor stochastic seed is inferred from the host machine's clock.
    
    Only parameters the user can actually vary are configurable here.
    The V1 arrival, service-time, and horizon semantics are model
    assumptions documented in MODEL_SEMANTICS.md, not fake choices.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    warmup_seconds: float = Field(default=300.0, ge=0.0)
    measurement_seconds: float = Field(default=3600.0, gt=0.0)
    replications: int = Field(default=20, ge=1)
    base_seed: int = Field(default=12345, ge=0)
    max_events_per_replication: int = Field(default=5_000_000, gt=0)
