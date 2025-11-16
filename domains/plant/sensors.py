from .model import ThermalPlant

class PlantSensors:
    def __init__(self, plant: ThermalPlant):
        self.plant = plant
    def read_temp(self) -> float:
        return self.plant.temp


from .model import PressurePlant

class PressureSensors:
    def __init__(self, plant: PressurePlant):
        self.plant = plant
    def read_pressure(self) -> float:
        return self.plant.pressure
