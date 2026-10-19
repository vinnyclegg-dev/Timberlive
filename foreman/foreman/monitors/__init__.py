"""Monitors (plain Python, no LLM). Importing this package registers every monitor.

Shared constants live here with their source, so a reader can check each one.
"""

# Edible goods only (CLAUDE.md "Food = edible goods only"; harness/watch.py FOOD). Raw Corn, Cassava,
# Soybean, Eggplant and Potato are ingredients until a Food Factory / Fermenter / Grill processes them.
FOOD = ("Berries", "Kohlrabi", "FermentedCassava", "FermentedSoybean", "FermentedMushroom", "CornRation",
        "EggplantRation", "AlgaeRation", "Carrot", "GrilledPotato", "Bread")
# Jobs that keep food and water flowing (harness/audit.py).
FOOD_JOBS = ("FarmHouse", "GathererFlag", "Fermenter", "FoodFactory", "HydroponicGarden", "Grill", "Bakery",
             "DeepWaterPump", "WaterPump", "MechanicalWaterPump", "AquaticFarmhouse")
FOOD_STORE_GOODS = {"Water", "Berries", "Kohlrabi", "Corn", "Mushroom", "Cassava", "Soybean", "Eggplant", "Potato",
                    "Carrot", "Wheat", "Algae", "FermentedCassava", "FermentedSoybean", "FermentedMushroom",
                    "CornRation", "EggplantRation", "AlgaeRation", "GrilledPotato", "Bread"}
# Nominal power use in hp (knowledge/09-buildings.md, game blueprints). Live demand reads 0 outside work hours.
POWER_USE = {"IndustrialLumberMill": 75, "GearWorkshop": 120, "Smelter": 200, "FoodFactory": 120, "Fermenter": 50,
             "OilPress": 50, "WoodWorkshop": 250, "CoffeeBrewery": 200, "Centrifuge": 200, "DeepMechanicalPump": 500,
             "AquiferDrill": 400, "Numbercruncher": 500, "CompactMechanicalPump": 700}
# Water per day used by buildings (harness/monitor.py, knowledge/09); beavers drink 2.6/day (measured S2E1).
BUILDING_WATER = {"BreedingPod": 1.0, "HydroponicGarden": 3.3, "SteamEngine": 7.2, "CoffeeBrewery": 12.0}
DRINK_PER_BEAVER = 2.6
EAT_PER_BEAVER = 3.0
LONGEST_HAZARD_DAYS = 7     # longest drought/badtide so far (S2E1); store key "longest_hazard_days" overrides
# Inputs a workshop starves without (knowledge/09 production chains).
INPUTS = {"Log": ("IndustrialLumberMill", "LumberMill"), "Plank": ("GearWorkshop", "WoodWorkshop"),
          "ScrapMetal": ("Smelter", "Metalsmith"), "Corn": ("FoodFactory",), "CanolaSeeds": ("OilPress",),
          "PineResin": ("WoodWorkshop",), "Algae": ("FoodFactory",)}
BATCH_MAKERS = ("HydroponicGarden", "OilPress", "Fermenter", "CoffeeBrewery")


def bid(b) -> str:
    return f'"{b.id}"'


from . import supply, buildings, population, stream, production, land, forecast, progress, ops, water, plan  # noqa: E402,F401
