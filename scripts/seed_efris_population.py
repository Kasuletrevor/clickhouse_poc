from __future__ import annotations

import argparse
import itertools
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.oracle import OracleDatabase

SIM_DIR = ROOT / "simulation"


def load_json(name: str):
    with (SIM_DIR / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(name: str, payload) -> None:
    with (SIM_DIR / name).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def build_population():
    blueprint = load_json("taxpayer_population.json")
    stations = load_json("stations.json")
    rng = random.Random(int(blueprint["seed"]))

    station_ids = [item["station_id"] for item in blueprint["station_distribution"]]
    station_weights = [item["weight"] for item in blueprint["station_distribution"]]

    combinations = list(
        itertools.product(
            blueprint["name_prefixes"],
            blueprint["business_activities"],
        )
    )
    rng.shuffle(combinations)

    count = int(blueprint["taxpayer_count"])
    if count > len(combinations):
        raise ValueError("taxpayer_count exceeds the available unique name combinations")

    taxpayers = []
    for index, (prefix, activity) in enumerate(combinations[:count], start=1):
        suffix = blueprint["name_suffixes"][(index - 1) % len(blueprint["name_suffixes"])]
        taxpayers.append(
            {
                "taxpayer_id": f"{blueprint['taxpayer_id_prefix']}{index:06d}",
                "taxpayer_name": f"{prefix} {activity} {suffix}",
                "taxpayer_type": blueprint["taxpayer_type"],
                "station_id": rng.choices(station_ids, weights=station_weights, k=1)[0],
                "traffic_weight": rng.randint(
                    int(blueprint["taxpayer_traffic_weight_min"]),
                    int(blueprint["taxpayer_traffic_weight_max"]),
                ),
            }
        )

    device_config = blueprint["devices"]
    target_devices = int(device_config["target_count"])
    if target_devices < count:
        raise ValueError("devices.target_count must be at least taxpayer_count")

    # Every taxpayer gets one device first. Additional devices are then spread
    # across taxpayers round-robin after a deterministic shuffle. With the
    # current 200/500 setup this produces 2 or 3 devices per taxpayer.
    device_counts = {taxpayer["taxpayer_id"]: 1 for taxpayer in taxpayers}
    remaining = target_devices - count
    order = [taxpayer["taxpayer_id"] for taxpayer in taxpayers]
    rng.shuffle(order)
    pointer = 0
    while remaining > 0:
        taxpayer_id = order[pointer % len(order)]
        device_counts[taxpayer_id] += 1
        remaining -= 1
        pointer += 1

    type_names = [item["name"] for item in device_config["types"]]
    type_weights = [item["weight"] for item in device_config["types"]]

    devices = []
    for taxpayer in taxpayers:
        taxpayer_id = taxpayer["taxpayer_id"]
        for sequence in range(1, device_counts[taxpayer_id] + 1):
            devices.append(
                {
                    "device_no": f"{taxpayer_id}_{sequence:02d}",
                    "taxpayer_id": taxpayer_id,
                    "device_seq": sequence,
                    "device_type": rng.choices(type_names, weights=type_weights, k=1)[0],
                    "traffic_weight": rng.randint(
                        int(device_config["traffic_weight_min"]),
                        int(device_config["traffic_weight_max"]),
                    ),
                }
            )

    known_station_ids = {station["station_id"] for station in stations}
    unknown = sorted({t["station_id"] for t in taxpayers} - known_station_ids)
    if unknown:
        raise ValueError(f"taxpayer blueprint references unknown stations: {unknown}")

    return stations, taxpayers, devices


def export_population(stations, taxpayers, devices) -> None:
    write_json("generated_taxpayers.json", taxpayers)
    write_json("generated_devices.json", devices)
    print(f"Exported {len(taxpayers)} taxpayers to simulation/generated_taxpayers.json")
    print(f"Exported {len(devices)} devices to simulation/generated_devices.json")


def seed_oracle(stations, taxpayers, devices) -> None:
    db = OracleDatabase(get_settings())

    merge_station = """
        MERGE INTO STATION target
        USING (
            SELECT :station_id STATION_ID,
                   :station_name STATION_NAME,
                   :region REGION,
                   :district DISTRICT
            FROM DUAL
        ) source
        ON (target.STATION_ID = source.STATION_ID)
        WHEN MATCHED THEN UPDATE SET
            target.STATION_NAME = source.STATION_NAME,
            target.REGION = source.REGION,
            target.DISTRICT = source.DISTRICT,
            target.UPDATED_AT = SYSTIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (STATION_ID, STATION_NAME, REGION, DISTRICT, UPDATED_AT)
        VALUES
            (source.STATION_ID, source.STATION_NAME, source.REGION, source.DISTRICT, SYSTIMESTAMP)
    """

    merge_taxpayer = """
        MERGE INTO TAXPAYER target
        USING (
            SELECT :taxpayer_id TAXPAYER_ID,
                   :taxpayer_name TAXPAYER_NAME,
                   :taxpayer_type TAXPAYER_TYPE,
                   :station_id STATION_ID
            FROM DUAL
        ) source
        ON (target.TAXPAYER_ID = source.TAXPAYER_ID)
        WHEN MATCHED THEN UPDATE SET
            target.TAXPAYER_NAME = source.TAXPAYER_NAME,
            target.TAXPAYER_TYPE = source.TAXPAYER_TYPE,
            target.STATION_ID = source.STATION_ID,
            target.UPDATED_AT = SYSTIMESTAMP
        WHEN NOT MATCHED THEN INSERT
            (TAXPAYER_ID, TAXPAYER_NAME, TAXPAYER_TYPE, STATION_ID, UPDATED_AT)
        VALUES
            (source.TAXPAYER_ID, source.TAXPAYER_NAME, source.TAXPAYER_TYPE, source.STATION_ID, SYSTIMESTAMP)
    """

    merge_device = """
        MERGE INTO EFRIS_DEVICE target
        USING (
            SELECT :device_no DEVICE_NO,
                   :taxpayer_id TAXPAYER_ID,
                   :device_seq DEVICE_SEQ,
                   :device_type DEVICE_TYPE
            FROM DUAL
        ) source
        ON (target.DEVICE_NO = source.DEVICE_NO)
        WHEN MATCHED THEN UPDATE SET
            target.TAXPAYER_ID = source.TAXPAYER_ID,
            target.DEVICE_SEQ = source.DEVICE_SEQ,
            target.DEVICE_TYPE = source.DEVICE_TYPE
        WHEN NOT MATCHED THEN INSERT
            (DEVICE_NO, TAXPAYER_ID, DEVICE_SEQ, DEVICE_TYPE)
        VALUES
            (source.DEVICE_NO, source.TAXPAYER_ID, source.DEVICE_SEQ, source.DEVICE_TYPE)
    """

    with db.connection() as conn:
        with conn.cursor() as cursor:
            for station in stations:
                cursor.execute(merge_station, station)

            for taxpayer in taxpayers:
                cursor.execute(
                    merge_taxpayer,
                    {
                        "taxpayer_id": taxpayer["taxpayer_id"],
                        "taxpayer_name": taxpayer["taxpayer_name"],
                        "taxpayer_type": taxpayer["taxpayer_type"],
                        "station_id": taxpayer["station_id"],
                    },
                )

            for device in devices:
                cursor.execute(
                    merge_device,
                    {
                        "device_no": device["device_no"],
                        "taxpayer_id": device["taxpayer_id"],
                        "device_seq": device["device_seq"],
                        "device_type": device["device_type"],
                    },
                )

        conn.commit()

    print(
        "Oracle seed committed: "
        f"{len(stations)} stations, {len(taxpayers)} taxpayers, {len(devices)} devices"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and seed the synthetic EFRIS station/taxpayer/device population."
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Generate JSON files but do not write anything to Oracle.",
    )
    args = parser.parse_args()

    stations, taxpayers, devices = build_population()
    export_population(stations, taxpayers, devices)

    print(
        f"Population ready: {len(stations)} stations, "
        f"{len(taxpayers)} taxpayers, {len(devices)} devices"
    )

    if not args.export_only:
        seed_oracle(stations, taxpayers, devices)


if __name__ == "__main__":
    main()
