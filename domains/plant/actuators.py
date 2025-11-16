from .model import ThermalPlant

class PlantActuators:
    def __init__(self, plant: ThermalPlant):
        self.plant = plant
    def set_heater_power(self, p: float):
        self.plant.heater = max(0.0, min(1.0, p))
    def open_valve(self, valve: str, u: float):
        # we only have a cooling valve in this demo
        self.plant.cool = max(0.0, min(1.0, u))
    def noop(self):
        pass


from .model import PressurePlant

class PressureActuators:
    def __init__(self, plant: PressurePlant):
        self.plant = plant
    def set_inflow(self, q: float):
        self.plant.inflow = max(0.0, min(1.0, q))
    def open_relief(self, u: float):
        self.plant.relief = max(0.0, min(1.0, u))
