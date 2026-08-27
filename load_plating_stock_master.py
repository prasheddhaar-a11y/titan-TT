"""
Loads Plating Stock Master data (ModelMaster) and per-model Jig Capacity
(Jig_Loading.JigLoadingMaster) from plating_stock_master_data.csv, which is
generated directly from 'All SKU and Details 1.xlsx' by
extract_plating_stock_master.py (2,591 rows, every cell read with openpyxl -
nothing hand-transcribed).

Only columns that map 1:1 to an existing DB field are loaded:

    plating_stk_no  <- Plating Stock No
    model_no        <- Basic Stock No
    version         <- Basic Stk No_Version, with the Basic Stock No prefix
                        stripped off (e.g. "10005A" - "10005" -> "A")
    brand           <- BRAND
    gender          <- Gender
    polish_finish   <- Pol Finish (reused/created by exact text match -
                        e.g. "Buffed", "Bi-Finish", "Shotblasting", "AL")
    ep_bath_type    <- Bath Type
    wiping_required <- IP Wiping (Yes -> True, No/NA -> False)
    tray_capacity   <- Jig Qty
    tray_type       <- Traycate (Normal/Jumbo, case-insensitive); left NULL
                        where the sheet itself only showed "?"
    JigLoadingMaster.jig_capacity <- Jig Qty (per user request: Jig ID /
                        jig capacity per model)
    JigLoadingMaster.jig_type     <- Traycate, as shown in the sheet

Every other column (PMR TAG, AMS, CC-Plating grp, Spider/Spindle, IP MC,
In process Tray Color, Look like models, Finish @ Loc, Basic Stk
No_Pol Finish, Plating Input stock No, Polishing Stock No) has no matching
field in ModelMaster/JigLoadingMaster and is intentionally NOT loaded -
nothing was invented for it.

Rows where the sheet showed "?" for Traycate are loaded with tray_type left
unset rather than guessed - see the flagged list printed at the end.

Usage:
    python load_plating_stock_master.py
"""
import csv
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "watchcase_tracker.settings")
django.setup()

from django.contrib.auth.models import User
from django.db import transaction

from modelmasterapp.models import ModelMaster, PolishFinishType, TrayType
from Jig_Loading.models import JigLoadingMaster

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plating_stock_master_data.csv")


def main():
    admin_user = User.objects.filter(is_superuser=True).first()

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    created, updated, flagged = 0, 0, []
    polish_cache = {}
    traytype_cache = {t.tray_type.strip().lower(): t for t in TrayType.objects.all()}

    with transaction.atomic():
        for row in rows:
            plating_stk_no = row["plating_stk_no"].strip()
            model_no = row["model_no"].strip()
            version = row["version"].strip()

            pol_finish_text = row["pol_finish"].strip()
            polish_finish_obj = None
            if pol_finish_text:
                polish_finish_obj = polish_cache.get(pol_finish_text)
                if polish_finish_obj is None:
                    polish_finish_obj, _ = PolishFinishType.objects.get_or_create(
                        polish_finish=pol_finish_text,
                        defaults={"polish_internal": pol_finish_text.upper().replace(" ", "_")},
                    )
                    polish_cache[pol_finish_text] = polish_finish_obj

            traycate_raw = row["traycate"].strip()
            tray_type_obj = traytype_cache.get(traycate_raw.lower())
            if tray_type_obj is None:
                flagged.append(f"{plating_stk_no}: Traycate was '{traycate_raw}' in source sheet, tray_type left unset")

            ip_wiping_raw = row["ip_wiping"].strip()
            if ip_wiping_raw == "Yes":
                wiping_required = True
            elif ip_wiping_raw in ("No", "NA", ""):
                wiping_required = False
            else:
                wiping_required = False
                flagged.append(
                    f"{plating_stk_no}: IP Wiping was unrecognized ('{ip_wiping_raw}') in source sheet, "
                    f"defaulted to False - verify against real sheet"
                )

            jig_qty = int(row["jig_qty"]) if row["jig_qty"].strip().isdigit() else None
            if jig_qty is None:
                flagged.append(f"{plating_stk_no}: Jig Qty was '{row['jig_qty']}' (non-numeric), tray_capacity/jig_capacity left unset")

            obj, was_created = ModelMaster.objects.update_or_create(
                plating_stk_no=plating_stk_no,
                defaults={
                    "model_no": model_no,
                    "version": version,
                    "brand": row["brand"].strip(),
                    "gender": row["gender"].strip(),
                    "polish_finish": polish_finish_obj,
                    "ep_bath_type": row["bath_type"].strip(),
                    "wiping_required": wiping_required,
                    "tray_type": tray_type_obj,
                    "tray_capacity": jig_qty,
                    "createdby": admin_user,
                },
            )
            created += 1 if was_created else 0
            updated += 0 if was_created else 1

            JigLoadingMaster.objects.update_or_create(
                model_stock_no=obj,
                defaults={
                    "jig_type": traycate_raw,
                    "jig_capacity": jig_qty or 0,
                    "forging_info": "",
                },
            )

    print(f"ModelMaster: {created} created, {updated} updated ({created + updated} total rows processed)")
    print(f"JigLoadingMaster: {created + updated} rows upserted (jig_capacity = Jig Qty per model)")
    if flagged:
        print(f"\n{len(flagged)} row(s) flagged for manual verification against the real sheet:")
        for line in flagged:
            print(f"  - {line}")


if __name__ == "__main__":
    main()
