# domains/plant/model.py
from dataclasses import dataclass

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))

@dataclass
class PlantSim:
    """
    Simple first-order thermal plant:
      dT/dt = -k_cool * valve * (T - T_ambient) + k_heat
    Chosen for stability + deterministic behavior under perfect conditions.
    """
    T: float = 85.0            # initial temperature (°C)
    T_ambient: float = 25.0    # ambient (°C)
    valve: float = 0.0         # 0..1 (cooling valve opening)
    k_cool: float = 0.35       # cooling gain
    k_heat: float = 0.02       # background heat leak

    def step(self, dt: float):
        dTdt = -self.k_cool * self.valve * (self.T - self.T_ambient) + self.k_heat
        self.T += dTdt * dt

class Sensors:
    def __init__(self, plant: PlantSim):
        self._plant = plant

    def read_temp(self) -> float:
        # perfect conditions → no noise
        return float(self._plant.T)
    
    def read_pressure(self) -> float:
        # Pressure demo reuses same scalar state internally (T)
        return float(self._plant.T)

    # Optional: consistent naming if any demo calls 'read_p'
    def read_p(self) -> float:
        return self.read_pressure()


class Actuators:
    def __init__(self, plant: PlantSim):
        self._plant = plant

    def open_valve(self, name: str, u: float):
        # only one cooling/relief valve in this toy model
        self._plant.valve = clamp(u, 0.0, 1.0)

    # --- Pressure demo synonyms & tolerant signatures ---
    def open_relief(self, *args):
        """
        Accepts either:
          open_relief(u)
        or
          open_relief(name, u)
        """
        if len(args) == 1:
            u = float(args[0])
        elif len(args) == 2:
            # name is ignored in this unified plant
            u = float(args[1])
        else:
            raise TypeError("open_relief expects (u) or (name, u)")
        self.open_valve("relief", u)

    def open_vent(self, *args):
        """
        Accepts either:
          open_vent(u)
        or
          open_vent(name, u)
        """
        if len(args) == 1:
            u = float(args[0])
        elif len(args) == 2:
            u = float(args[1])
        else:
            raise TypeError("open_vent expects (u) or (name, u)")
        self.open_valve("vent", u)

    def set_valve(self, name: str, u: float):
        self.open_valve(name, u)

    def set_relief(self, name: str, u: float):
        self.open_valve(name, u)

    # --- No-ops for compatibility with thermal demos ---
    def set_heater_power(self, p: float):
        # Unified plant doesn't model a heater explicitly; safe no-op
        pass

    def noop(self):
        pass



# --- Back-compat aliases for older demos ---
ThermalPlant = PlantSim
PressurePlant = PlantSim

def make_plant(*, temp=None, T=None, T_env=None, T_ambient=None,
               pressure=None, p=None, p_env=None, p_ambient=None,
               valve=0.0, k_cool=0.35, k_heat=0.02) -> PlantSim:
    """
    Back-compat factory that accepts legacy names (temp/T_env) for thermal
    or (pressure/p_env) for pressure demos. Uses the same PlantSim model.
    """

    # --- Thermal aliases ---
    if T is None:
        if temp is not None:
            T = float(temp)
        elif pressure is not None:
            T = float(pressure)       # reuse same internal var
        else:
            T = 85.0
    if T_ambient is None:
        if T_env is not None:
            T_ambient = float(T_env)
        elif p_env is not None:
            T_ambient = float(p_env)
        else:
            T_ambient = 25.0

    # create instance
    return PlantSim(T=T, T_ambient=T_ambient, valve=valve,
                    k_cool=k_cool, k_heat=k_heat)

