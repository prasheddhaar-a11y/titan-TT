"""
Read-only selectors for the Reports module.

Consolidated Report: one row per Plating Stock No showing the complete
journey (Day Planning -> ... -> Spider Spindle Z2). The exact same row
builder is used by both the Preview API and the Excel download so the
two can never diverge.
"""
import logging
from datetime import datetime, time

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

# Stage order for the consolidated journey (spec order)
STAGE_DAY_PLANNING = 'Day Planning'
STAGE_INPUT_SCREENING = 'Input Screening'
STAGE_BRASS_QC = 'Brass QC'
STAGE_IQF = 'IQF'
STAGE_BRASS_AUDIT = 'Brass Audit'
STAGE_JIG_LOADING = 'Jig Loading'
STAGE_IP_INSPECTION = 'IP Inspection'
STAGE_JIG_UNLOADING = 'Jig Unloading'
STAGE_NICKEL_WIPING = 'Nickel Wiping'
STAGE_NICKEL_AUDIT = 'Nickel Audit'
STAGE_SS_Z1 = 'Spider Spindle Zone 1'
STAGE_SS_Z2 = 'Spider Spindle Zone 2'

STAGE_FLOW = [
    STAGE_DAY_PLANNING,
    STAGE_INPUT_SCREENING,
    STAGE_BRASS_QC,
    STAGE_IQF,
    STAGE_BRASS_AUDIT,
    STAGE_JIG_LOADING,
    STAGE_IP_INSPECTION,
    STAGE_JIG_UNLOADING,
    STAGE_NICKEL_WIPING,
    STAGE_NICKEL_AUDIT,
    STAGE_SS_Z1,
    STAGE_SS_Z2,
]

# IQF is an optional branch: only part of a lot's journey when it was
# actually routed there. Skipped as "Next Stage" unless flagged.
OPTIONAL_STAGES = {STAGE_IQF}

DT_FORMAT = '%d-%b-%Y %I:%M %p'


def _fmt(dt):
    if not dt:
        return ''
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime(DT_FORMAT)


def _normalize_unload_lot_id(value):
    """Same normalization the Jig Unloading report uses."""
    value = str(value or '').strip().lstrip('-')
    if ':' in value:
        value = value.rsplit(':', 1)[-1].strip()
    if value.startswith('JLOT-') and '-' in value[5:]:
        value = value.rsplit('-', 1)[-1]
    return value


def _first_remark(*values):
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ''


def _completed_stages(stock, batch, jig_record, unload_record):
    """
    Return (stages, final_status) where stages is an ordered list of
    dicts {name, out} for every completed stage of this lot and
    final_status is 'Accept' / 'Reject' from the latest inspection.
    """
    stages = []
    final_status = ''

    def add(name, out_time):
        stages.append({'name': name, 'out': out_time})

    # 1. Day Planning — completed once the lot was released / trays scanned
    if batch and (batch.Moved_to_D_Picker or stock.tray_scan_status):
        add(STAGE_DAY_PLANNING, stock.created_at)

    # 2. Input Screening
    if (stock.accepted_Ip_stock or stock.rejected_ip_stock
            or (stock.few_cases_accepted_Ip_stock and not stock.ip_onhold_picking)):
        add(STAGE_INPUT_SCREENING, stock.last_process_date_time or stock.created_at)
        final_status = 'Reject' if stock.rejected_ip_stock else 'Accept'

    # 3. Brass QC
    if (stock.brass_qc_accptance or stock.brass_qc_rejection
            or (stock.brass_qc_few_cases_accptance and not stock.brass_onhold_picking)):
        add(STAGE_BRASS_QC, stock.bq_last_process_date_time)
        final_status = 'Reject' if stock.brass_qc_rejection else 'Accept'

    # 4. IQF (optional branch)
    if (stock.iqf_acceptance or stock.iqf_rejection
            or (stock.iqf_few_cases_acceptance and not stock.iqf_onhold_picking)):
        add(STAGE_IQF, stock.iqf_last_process_date_time)
        final_status = 'Reject' if stock.iqf_rejection else 'Accept'

    # 5. Brass Audit
    if (stock.brass_audit_accptance or stock.brass_audit_rejection
            or (stock.brass_audit_few_cases_accptance and not stock.brass_audit_onhold_picking)):
        add(STAGE_BRASS_AUDIT, stock.brass_audit_last_process_date_time)
        final_status = 'Reject' if stock.brass_audit_rejection else 'Accept'

    # 6. Jig Loading — a submitted JigCompleted record exists for the lot
    if jig_record:
        add(STAGE_JIG_LOADING, jig_record.updated_at)

    # 7. IP Inspection — jig has been positioned in a bath
    if jig_record and jig_record.jig_position:
        add(STAGE_IP_INSPECTION, jig_record.updated_at)

    # 8. Jig Unloading — lot appears in a JigUnloadAfterTable record
    if unload_record:
        add(STAGE_JIG_UNLOADING, unload_record.Un_loaded_date_time)

        # 9. Nickel Wiping (Nickel Inspection)
        if (unload_record.nq_qc_accptance or unload_record.nq_qc_rejection
                or (unload_record.nq_qc_few_cases_accptance
                    and not unload_record.nq_onhold_picking)):
            add(STAGE_NICKEL_WIPING, unload_record.nq_last_process_date_time)
            final_status = 'Reject' if unload_record.nq_qc_rejection else 'Accept'

        # 10. Nickel Audit
        if (unload_record.na_qc_accptance or unload_record.na_qc_rejection
                or (unload_record.na_qc_few_cases_accptance
                    and not unload_record.na_onhold_picking)):
            add(STAGE_NICKEL_AUDIT, unload_record.na_last_process_date_time)
            final_status = 'Reject' if unload_record.na_qc_rejection else 'Accept'

        # 11 / 12. Spider Spindle zones
        if getattr(unload_record, 'ss_z1_completed', False):
            add(STAGE_SS_Z1, getattr(unload_record, 'ss_z1_completed_at', None))
        if getattr(unload_record, 'ss_z2_completed', False):
            add(STAGE_SS_Z2, getattr(unload_record, 'ss_z2_completed_at', None))

    return stages, final_status


def _next_stage(current_name, final_status, stock):
    """First pending stage after the current one, honoring branches."""
    if final_status == 'Reject':
        return None  # journey ends on rejection
    if current_name == STAGE_SS_Z2:
        return None
    try:
        idx = STAGE_FLOW.index(current_name)
    except ValueError:
        return STAGE_FLOW[0]
    for name in STAGE_FLOW[idx + 1:]:
        if name in OPTIONAL_STAGES:
            # only route through IQF when the lot was actually sent there
            if not getattr(stock, 'send_brass_audit_to_iqf', False):
                continue
        return name
    return None


def get_consolidated_report_rows(date_from=None, date_to=None, plating_stock_no=''):
    """
    Build the consolidated journey rows. One row per Plating Stock No,
    using the record with the most recent stage activity.

    date_from / date_to filter on the latest stage activity timestamp.
    plating_stock_no is a partial (icontains) match.
    """
    from modelmasterapp.models import TotalStockModel
    from Jig_Loading.models import JigCompleted
    from Jig_Unloading.models import JigUnloadAfterTable

    stock_qs = TotalStockModel.objects.filter(
        batch_id__isnull=False,
        batch_id__total_batch_quantity__gt=0,
        remove_lot=False,
    ).select_related('batch_id').order_by('-created_at')

    if plating_stock_no:
        stock_qs = stock_qs.filter(
            batch_id__plating_stk_no__icontains=plating_stock_no.strip()
        )

    stocks = list(stock_qs)
    lot_ids = {s.lot_id for s in stocks if s.lot_id}

    # Bulk maps — avoid N+1
    jig_by_lot = {}
    for record in JigCompleted.objects.filter(
        draft_status='submitted'
    ).order_by('updated_at').only(
        'lot_id', 'jig_position', 'updated_at', 'pick_remarks',
        'remarks', 'unloading_remarks', 'multi_model_allocation',
    ):
        keys = {record.lot_id}
        for allocation in record.multi_model_allocation or []:
            if isinstance(allocation, dict) and allocation.get('lot_id'):
                keys.add(str(allocation['lot_id']))
        for key in keys:
            if key in lot_ids:
                jig_by_lot[key] = record  # latest submitted wins

    unload_by_lot = {}
    for record in JigUnloadAfterTable.objects.all().order_by('Un_loaded_date_time'):
        keys = {_normalize_unload_lot_id(record.lot_id)}
        for combined in record.combine_lot_ids or []:
            keys.add(_normalize_unload_lot_id(combined))
        for key in keys:
            if key in lot_ids:
                unload_by_lot[key] = record

    tz_aware = timezone.is_aware(timezone.now())

    def to_dt(d, end=False):
        dt = datetime.combine(d, time.max if end else time.min)
        return timezone.make_aware(dt) if tz_aware else dt

    from_dt = to_dt(date_from) if date_from else None
    to_dt_val = to_dt(date_to, end=True) if date_to else None

    best_by_stk = {}
    for stock in stocks:
        batch = stock.batch_id
        stk_no = (batch.plating_stk_no or '').strip()
        if not stk_no:
            continue

        jig_record = jig_by_lot.get(stock.lot_id)
        unload_record = unload_by_lot.get(stock.lot_id)
        stages, final_status = _completed_stages(stock, batch, jig_record, unload_record)

        if stages:
            current = stages[-1]
            in_time = stages[-2]['out'] if len(stages) > 1 else stock.created_at
            activity = current['out'] or in_time or stock.created_at
        else:
            current = None
            in_time = None
            activity = stock.created_at

        # Date-range filter on latest stage activity
        if from_dt and (not activity or activity < from_dt):
            continue
        if to_dt_val and activity and activity > to_dt_val:
            continue

        if current:
            current_stage = (
                f"{current['name']}\nIN : {_fmt(in_time)}\nOUT: {_fmt(current['out'])}"
            )
            next_name = _next_stage(current['name'], final_status, stock)
        else:
            current_stage = f"{STAGE_DAY_PLANNING}\nIN : {_fmt(stock.created_at)}"
            next_name = STAGE_INPUT_SCREENING

        if next_name:
            next_stage = f"{next_name}\nIN : {_fmt(current['out'] if current else stock.created_at)}"
        else:
            next_stage = 'Completed'

        remarks = _first_remark(
            getattr(unload_record, 'spider_pick_remarks', None) if unload_record else None,
            getattr(unload_record, 'na_pick_remarks', None) if unload_record else None,
            getattr(unload_record, 'nq_pick_remarks', None) if unload_record else None,
            getattr(jig_record, 'unloading_remarks', None) if jig_record else None,
            getattr(jig_record, 'pick_remarks', None) if jig_record else None,
            getattr(jig_record, 'remarks', None) if jig_record else None,
            stock.BA_pick_remarks, stock.IQF_pick_remarks,
            stock.Bq_pick_remarks, stock.IP_pick_remarks,
            batch.dp_pick_remarks,
        )

        row = {
            'plating_stk_no': stk_no,
            'lot_qty': int(stock.total_stock or batch.total_batch_quantity or 0),
            'accept_reject': final_status,
            'current_stage': current_stage,
            'next_stage': next_stage,
            'remarks': remarks,
            '_activity': activity,
        }

        existing = best_by_stk.get(stk_no)
        if (
            existing is None
            or (row['_activity'] and not existing['_activity'])
            or (row['_activity'] and existing['_activity']
                and row['_activity'] > existing['_activity'])
        ):
            best_by_stk[stk_no] = row

    sentinel = datetime.min
    if tz_aware:
        sentinel = timezone.make_aware(datetime(1, 1, 2))
    rows = sorted(
        best_by_stk.values(),
        key=lambda r: r['_activity'] or sentinel,
        reverse=True,
    )
    for idx, row in enumerate(rows, start=1):
        row['s_no'] = idx
        row.pop('_activity', None)
    return rows


def search_plating_stock(query, limit=15):
    """
    Autocomplete for Plating Stock No. Uses Elasticsearch when configured
    (settings.ELASTICSEARCH_URL + elasticsearch package installed),
    otherwise falls back to an indexed DB partial match.
    """
    from modelmasterapp.models import ModelMasterCreation

    query = (query or '').strip()
    if not query:
        return []

    es_url = getattr(settings, 'ELASTICSEARCH_URL', None)
    if es_url:
        try:
            from elasticsearch import Elasticsearch

            client = Elasticsearch(es_url, request_timeout=2)
            response = client.search(
                index=getattr(settings, 'ELASTICSEARCH_PLATING_INDEX', 'plating_stock'),
                query={'match_phrase_prefix': {'plating_stk_no': query}},
                size=limit,
            )
            hits = [
                hit['_source'].get('plating_stk_no')
                for hit in response.get('hits', {}).get('hits', [])
            ]
            results = sorted({h for h in hits if h})
            if results:
                return results[:limit]
        except Exception:
            logger.warning('Elasticsearch autocomplete failed; using DB fallback', exc_info=True)

    # DB fallback: union of batch stock numbers (ModelMasterCreation, the
    # source the consolidated report uses) and the ModelMaster catalogue,
    # so every known plating stock number is suggested while typing.
    from modelmasterapp.models import ModelMaster

    def _matches(model):
        return model.objects.filter(
            plating_stk_no__icontains=query
        ).exclude(
            plating_stk_no__isnull=True
        ).exclude(
            plating_stk_no=''
        ).values_list('plating_stk_no', flat=True).distinct()

    combined = set(_matches(ModelMasterCreation)) | set(_matches(ModelMaster))
    q_lower = query.lower()
    # prefix matches first, then alphabetical
    return sorted(
        combined,
        key=lambda v: (not v.lower().startswith(q_lower), v),
    )[:limit]
