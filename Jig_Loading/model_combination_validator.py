"""
Model Combination Validator — DB-driven eligibility check for Jig Loading "Add Model" flow.

Architecture:
- Eligibility is determined ENTIRELY by the ModelMicroGroup table (single source of truth).
- No prefix-based hardcoding. No color codes. No lookalike logic here.
- Frontend renders; backend decides which models are eligible.
- New groups / models are added via Django admin — zero code changes required.

Flow:
    1. Receive selected_models (list of plating_stk_nos already on the jig).
    2. Use the primary model (selected_models[0]) to find its micro group.
    3. Fetch all active models from that micro group.
    4. Exclude already-selected models.
    5. Return eligible_models list (compatible response format for existing frontend).
"""
import logging

logger = logging.getLogger(__name__)


def validate_model_combination(selected_models):
    """
    Determine which models are eligible to add alongside the already-selected models.

    Args:
        selected_models: list of plating_stk_no strings currently on the jig.
                         selected_models[0] is treated as the primary model.

    Returns dict (backward-compatible format):
        {
            'eligible_models':               [{'plating_stk_no', 'model_no', 'ep_bath_type', 'jig_capacity'}, ...],
            'non_eligible_models':           [],
            'blocked_lookalike_plating_stk_nos': [],
            'warnings':                      [],
            'errors':                        [],
        }
    """
    eligible_models = []
    errors = []

    if not selected_models:
        errors.append('No models selected.')
        logger.warning('[VALIDATE] Called with empty selected_models')
        return _make_response(eligible_models, errors)

    selected_models = [s.strip() for s in selected_models if s and s.strip()]
    primary_psn = selected_models[0]

    logger.info(f'[VALIDATE] primary_psn={primary_psn} selected_models={selected_models}')

    try:
        from Jig_Loading.models import ModelMicroGroup
        from modelmasterapp.models import ModelMaster

        # Find the micro group for the primary model
        group_entry = ModelMicroGroup.objects.filter(
            plating_stk_no=primary_psn,
            is_active=True,
        ).first()

        if not group_entry:
            errors.append(
                f'Model "{primary_psn}" has no micro group assigned. '
                'Please contact admin to add it to a group.'
            )
            logger.warning(f'[VALIDATE] No micro group found for primary_psn={primary_psn}')
            return _make_response(eligible_models, errors)

        group_name = group_entry.group_name
        logger.info(f'[VALIDATE] primary_psn={primary_psn} → group_name={group_name}')

        # STRICT SSOT RULE:
        # every already-selected model must belong to the same micro group as primary.
        # If any selected model is outside the group, stop and return no-compatible.
        selected_group_rows = ModelMicroGroup.objects.filter(
            plating_stk_no__in=selected_models,
            is_active=True,
        ).values('plating_stk_no', 'group_name')
        selected_group_map = {row['plating_stk_no']: row['group_name'] for row in selected_group_rows}

        invalid_selected = []
        for psn in selected_models:
            if selected_group_map.get(psn) != group_name:
                invalid_selected.append(psn)

        if invalid_selected:
            logger.warning(
                '[VALIDATE] Group mismatch selected_models=%s primary_group=%s invalid=%s',
                selected_models,
                group_name,
                invalid_selected,
            )
            errors.append('No compatible models found')
            return _make_response(eligible_models, errors)

        # Fetch all active models in the same group, excluding already-selected ones
        eligible_psns = list(
            ModelMicroGroup.objects.filter(group_name=group_name, is_active=True)
            .exclude(plating_stk_no__in=selected_models)
            .values_list('plating_stk_no', flat=True)
        )

        logger.info(f'[VALIDATE] group={group_name} eligible_psns={eligible_psns}')

        if not eligible_psns:
            errors.append('No compatible models found')
            return _make_response(eligible_models, errors)

        # Enrich with ModelMaster display data (model_no, ep_bath_type)
        mm_lookup = {
            mm['plating_stk_no']: mm
            for mm in ModelMaster.objects.filter(
                plating_stk_no__in=eligible_psns
            ).values('plating_stk_no', 'model_no', 'ep_bath_type')
        }

        for psn in eligible_psns:
            mm = mm_lookup.get(psn, {})
            eligible_models.append({
                'plating_stk_no': psn,
                'model_no': mm.get('model_no', ''),
                'ep_bath_type': mm.get('ep_bath_type', ''),
                'jig_capacity': 0,
            })

        # Sort: put models registered in ModelMaster first, then by plating_stk_no
        eligible_models.sort(key=lambda m: (0 if m['model_no'] else 1, m['plating_stk_no']))

        logger.info(f'[VALIDATE] Result: eligible={len(eligible_models)} errors={errors}')

    except Exception as e:
        logger.exception(f'[VALIDATE] Unhandled exception: {e}')
        errors.append(f'Eligibility check failed: {str(e)}')

    return _make_response(eligible_models, errors)


def _make_response(eligible_models, errors=None):
    """Return backward-compatible response dict."""
    return {
        'eligible_models': eligible_models,
        'non_eligible_models': [],
        'blocked_lookalike_plating_stk_nos': [],
        'warnings': [],
        'errors': errors or [],
    }
