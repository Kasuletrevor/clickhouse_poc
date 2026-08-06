from __future__ import annotations

import json
import random
import time
from collections import defaultdict, deque
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

INSERT_SQL = """
    INSERT INTO T_INVOICE_ERROR_LOG
        (ID, TIN, DEVICE_NO, SELLER_REFERENCE_NO, RETURN_CODE, RETURN_MSG,
         GROSS_AMOUNT, TAX_AMOUNT, CURRENCY, ITEM_DESCRIPTION,
         CREATE_USER_ID, CREATE_DATE)
    VALUES
        (:source_id, :tin, :device_no, :seller_reference_no,
         :return_code, :return_msg, :gross_amount, :tax_amount,
         :currency, :item_description, :create_user_id, SYSDATE)
"""


def load_json(sim_dir: Path, name: str):
    with (Path(sim_dir) / name).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def weighted_choice(rng: random.Random, rows, weight_key: str = "weight"):
    return rng.choices(rows, weights=[float(row.get(weight_key, 1)) for row in rows], k=1)[0]


def money(value: int) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def vat_from_gross(gross: Decimal) -> Decimal:
    return (gross * Decimal("18") / Decimal("118")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def build_reference(cursor, tin: str) -> str:
    cursor.execute("SELECT SEQ_EFRIS_SELLER_REF.NEXTVAL FROM DUAL")
    return f"{tin}-INV-{int(cursor.fetchone()[0]):08d}"


def format_source_id(source_prefix: str, sequence: int) -> str:
    if sequence <= 0:
        raise ValueError("sequence must be greater than zero")
    value = f"{source_prefix}-{sequence:06d}"
    if len(value) > 32:
        raise ValueError("Simulator source ID exceeds T_INVOICE_ERROR_LOG.ID length")
    return value


class RatePacer:
    def __init__(self, rate: float, clock=time.perf_counter, sleeper=time.sleep):
        if rate <= 0:
            raise ValueError("rate must be greater than zero")
        self.rate = float(rate)
        self.interval = 1.0 / self.rate
        self.clock = clock
        self.sleeper = sleeper
        self.next_due = self.clock() + self.interval

    def reset(self) -> None:
        self.next_due = self.clock() + self.interval

    def wait_next(self) -> float:
        now = self.clock()
        delay = self.next_due - now
        if delay > 0:
            self.sleeper(delay)
        observed = self.clock()
        lag = max(0.0, observed - self.next_due)
        self.next_due += self.interval
        return lag


class EfrisEventFactory:
    def __init__(
        self,
        sim_dir: Path,
        source_prefix: str,
        seed: int,
        retry_probability: float,
        recent_reference_pool: int | None = None,
    ):
        self.sim_dir = Path(sim_dir)
        self.source_prefix = source_prefix
        self.rng = random.Random(seed)
        self.taxpayers = load_json(self.sim_dir, "generated_taxpayers.json")
        self.devices = load_json(self.sim_dir, "generated_devices.json")
        self.error_codes = load_json(self.sim_dir, "error_codes.json")
        self.products = load_json(self.sim_dir, "products.json")
        self.config = load_json(self.sim_dir, "config.json")
        if not self.taxpayers or not self.devices or not self.error_codes or not self.products:
            raise ValueError("Simulation population is empty. Run scripts/seed_efris_population.py first.")
        self.retry_probability = float(retry_probability)
        recent_limit = int(recent_reference_pool or self.config.get("recent_reference_pool", 5000))
        self.recent = deque(maxlen=recent_limit)
        self.gross_min = int(self.config["gross_amount_min"])
        self.gross_max = int(self.config["gross_amount_max"])
        self.currency = str(self.config["currency"])
        self.create_user_id = str(self.config["create_user_id"])
        self.devices_by_taxpayer = defaultdict(list)
        for device in self.devices:
            self.devices_by_taxpayer[device["taxpayer_id"]].append(device)

    def next_bindings(self, cursor, sequence: int) -> dict:
        is_retry = bool(self.recent) and self.rng.random() < self.retry_probability
        if is_retry:
            previous = self.rng.choice(tuple(self.recent))
            taxpayer = previous["taxpayer"]
            device = previous["device"]
            seller_reference_no = previous["seller_reference_no"]
            gross_amount = previous["gross_amount"]
            tax_amount = previous["tax_amount"]
            item_description = previous["item_description"]
        else:
            taxpayer = weighted_choice(self.rng, self.taxpayers, "traffic_weight")
            candidates = self.devices_by_taxpayer[taxpayer["taxpayer_id"]]
            if not candidates:
                raise RuntimeError(f"No EFRIS devices for taxpayer {taxpayer['taxpayer_id']}")
            device = weighted_choice(self.rng, candidates, "traffic_weight")
            seller_reference_no = build_reference(cursor, taxpayer["taxpayer_id"])
            gross_amount = money(self.rng.randint(self.gross_min, self.gross_max))
            tax_amount = vat_from_gross(gross_amount)
            item_description = self.rng.choice(self.products)

        error = weighted_choice(self.rng, self.error_codes)
        bindings = {
            "source_id": format_source_id(self.source_prefix, sequence),
            "tin": taxpayer["taxpayer_id"],
            "device_no": device["device_no"],
            "seller_reference_no": seller_reference_no,
            "return_code": str(error["code"]),
            "return_msg": str(error["message"])[:256],
            "gross_amount": gross_amount,
            "tax_amount": tax_amount,
            "currency": self.currency,
            "item_description": item_description,
            "create_user_id": self.create_user_id,
        }
        if not is_retry:
            self.recent.append({
                "taxpayer": taxpayer,
                "device": device,
                "seller_reference_no": seller_reference_no,
                "gross_amount": gross_amount,
                "tax_amount": tax_amount,
                "item_description": item_description,
            })
        return bindings
