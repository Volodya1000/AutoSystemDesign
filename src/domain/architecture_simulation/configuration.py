"""Validate reproducible, virtual-time simulation experiment settings."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ArrivalProcess(StrEnum):
    """Choose how external client requests enter the simulated system."""

    POISSON = "poisson"


class ServiceDistribution(StrEnum):
    """Describe the explicitly assumed per-node service-time family."""

    GAMMA_MOMENTS = "gamma_moments"


class HorizonPolicy(StrEnum):
    """Choose how outstanding requests are counted at the measurement end."""

    STOP_AT_HORIZON = "stop_at_horizon"


class SimulationConfiguration(BaseModel):
    """Configure independent replications in seconds of *virtual* time.

    This nested model is read through the root Pydantic AppSettings object;
    environment variables use ASD_SIMULATION__FIELD_NAME. Neither virtual
    time nor stochastic seed is inferred from the host machine's clock.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    warmup_seconds: float = Field(default=300.0, ge=0.0)
    measurement_seconds: float = Field(default=3600.0, gt=0.0)
    replications: int = Field(default=20, ge=1)
    base_seed: int = Field(default=12345, ge=0)
    max_events_per_replication: int = Field(default=5_000_000, gt=0)
    arrival_process: ArrivalProcess = ArrivalProcess.POISSON
    service_distribution: ServiceDistribution = ServiceDistribution.GAMMA_MOMENTS
    horizon_policy: HorizonPolicy = HorizonPolicy.STOP_AT_HORIZON
