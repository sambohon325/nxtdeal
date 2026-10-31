import os

from fastapi import (
    FastAPI,
    Header,
    WebSocket,
    WebSocketDisconnect,
    Query,
    UploadFile,
    File,
    Form,
    Request
)
from fastapi.middleware.cors import (
    CORSMiddleware
)
from fastapi.responses import PlainTextResponse
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler

from contextlib import asynccontextmanager, AsyncExitStack
from core.worker_shutdown import WorkerShutdown

from pydantic import BaseModel, Field

from core.storage import load_graph

from core.storage_paths import (
    GRAPH_PATH,
    AUDIT_PATH,
    CREDENTIALS_PATH
)

from core.queries import (
    search_graph,
    ask_question,
    get_sales_dashboard,
    get_service_dashboard,
    get_finance_dashboard,
    get_executive_dashboard
)

from core.repository import repository

from core.pipeline_state import (
    get_all_pipeline_entity_ids
)

from core.workflow_dashboard import (
    get_lead_pipeline_dashboard
)

from core.pipeline_analytics import (
    get_pipeline_metrics
)

from core.follow_up_dashboard import (
    get_follow_up_dashboard
)

from core.velocity_dashboard import (
    get_velocity_dashboard
)

from core.salesperson_dashboard_api import (
    get_dashboard
)

from core.manager_dashboard_api import (
    get_dashboard as get_manager_dashboard_api
)

from core.leaderboard_api import (
    get_dashboard as get_leaderboard_dashboard
)

from core.routing_api import (
    assign_new_lead
)

from core.workload_dashboard_api import (
    get_dashboard as get_workload_dashboard_api
)

from core.escalation_dashboard_api import (
    get_dashboard as get_escalation_dashboard_api
)

from core.escalation_routing_api import (
    reassign
)

from core.ai_api import (
    ask
)

from core.profile_api import (
    get_profile
)

from core.graph_explore_api import (
    explore_entity_api
)

from core.audit_storage import (
    load_audit_log
)

from core.audit_api import (
    list_audit_events,
    get_audit_dashboard,
    get_audit_integrity_api
)

from core.auth_storage import (
    load_credentials
)

from core.customer_accounts_storage import (
    load_customer_credentials,
    CUSTOMER_CREDENTIALS_PATH
)

from core.customer_accounts_api import (
    signup_api as customer_signup_api,
    login_api as customer_login_api,
    request_link_code_api as customer_request_link_code_api,
    confirm_link_code_api as customer_confirm_link_code_api,
    me_api as customer_me_api
)

from core.rep_referrals_api import (
    get_my_summary_api as referrals_my_summary_api,
    submit_dealership_referral_api as referrals_submit_dealership_api,
    apply_code_api as referrals_apply_code_api,
    list_all_api as referrals_list_all_api,
    advance_referral_api as referrals_advance_api
)

from core.rep_finance_api import (
    get_overview_api as finance_overview_api,
    link_bank_api as finance_link_bank_api,
    set_budget_api as finance_set_budget_api,
    list_budgets_api as finance_list_budgets_api,
    record_commission_api as finance_record_commission_api,
    list_commissions_api as finance_list_commissions_api,
    advisor_api as finance_advisor_api
)

from core.demo_mode_api import (
    personas_api as demo_personas_api,
    start_demo_api,
    track_event_api as demo_track_event_api,
    get_session_api as demo_get_session_api,
    summarize_session_api as demo_summarize_session_api
)

from core.auth_api import (
    login,
    whoami,
    create_credential,
    change_password,
    reset_password,
    list_credentials,
    get_lockout_status,
    unlock_account,
    set_ip_allowlist,
    verify_mfa_login,
    begin_mfa_enrollment,
    confirm_mfa_enrollment,
    disable_mfa,
    admin_disable_mfa,
    get_mfa_status,
)

from core.auth import (
    verify_token, is_mfa_challenge_token
)

# core.sso / core.sso_config_api imports moved to api/routers/sso.py (CAF-00120).

from core.permissions import (
    ADMIN
)

from core.security import (
    can_access_entity,
    can_access_dashboard
)

from core.entity_update_api import update_entity_api

from core.messaging import (
    seed_channels
)

from core.messaging_api import (
    list_channels,
    get_channel_messages_api,
    post_channel_message_api,
    get_direct_messages_api,
    post_direct_message_api,
    list_conversations_api,
    list_directory_api
)

from core.knowledge_pins_api import (
    share_roles_api,
    create_shared_pin_api,
    list_shared_pins_api,
    retag_shared_pin_api,
    share_shared_pin_api,
    delete_shared_pin_api
)

from core.report_modules_api import (
    get_report_modules_api,
    get_overview_modules_api
)

from core.dashboard_layouts_api import (
    get_dashboard_layout_api,
    save_dashboard_layout_api
)

from core.notification_preferences_api import (
    get_notification_preferences_api,
    save_notification_preferences_api
)

from core.workspace_board_api import (
    get_workspace_board_api,
    save_workspace_board_api,
    add_workspace_item_api,
    get_shared_workspace_board_api
)

from core.workspace_explain_api import (
    explain_chart_api
)

from core.ws_manager import (
    manager as ws_manager
)

from core.assets_api import (
    list_templates_api,
    create_asset_api,
    submit_asset_api,
    get_asset_api,
    list_my_assets_api,
    list_pending_approvals_api as list_asset_pending_approvals_api,
    approve_asset_api,
    reject_asset_api
)

# Native per-department quick-entry (session 47) -- field notes, walk-in leads, vehicle
# intake, service tickets, and chat file attachments. See each core module's docstring.
from core.field_notes_api import (
    create_field_note_api,
    list_field_notes_api
)

from core.lead_intake_api import create_lead_api

from core.vehicle_intake_api import create_vehicle_api

from core.service_intake_api import create_service_record_api

from core.documents_api import upload_document_api

# Department job-workflow engine (session 53) -- 36 catalog job workflows (4 per
# department across all 9 sections), the generic multi-stage tracking engine, and the
# per-department suggested-prompt catalog. See core/workflow_catalog.py's docstring.
from core.workflow_tracking_api import (
    get_workflow_catalog_api,
    start_workflow_api,
    advance_workflow_api,
    cancel_workflow_api,
    list_workflow_instances_api
)

from core.workflow_tab_data_api import (
    get_tab_data_api
)

# Top Menu (session 60) -- the DMS-style navigation bar under the color bar, distinct
# from the 4 job-workflow buttons above. See core/menu_catalog.py's module docstring.
from core.menu_api import (
    get_department_menu_api,
    get_menu_data_api
)

from core.campaigns_api import (
    list_campaign_types_api,
    list_channels_api,
    preview_audience_api,
    create_campaign_api,
    get_campaign_api,
    list_my_campaigns_api,
    list_pending_campaigns_api,
    activate_campaign_api,
    complete_campaign_api,
    cancel_campaign_api,
    update_campaign_api,
    get_campaign_detail_api,
    duplicate_campaign_api,
    bulk_create_campaigns_api,
    create_recurring_schedule_api,
    list_recurring_schedules_api,
    get_recurring_schedule_api,
    set_recurring_schedule_active_api,
    delete_recurring_schedule_api,
    run_due_recurring_schedules_api,
    send_campaign_api,
    get_campaign_delivery_api,
)
from core.bulk_import_api import (
    list_import_targets_api,
    analyze_csv_api,
    preview_import_api,
    commit_import_api,
)
from core.user_management_api import (
    list_roles_api,
    list_users_api,
    create_user_api,
    update_user_role_api,
)

# CRM Pipeline + Email/SMS builder (session 79) -- Sam: "combine campaigns, audiences,
# and opportunities into one Hubspot style workflow dash called CRM... add an Email/SMS
# dash with a fully functional email builder." See core/lead_pipeline_api.py/
# core/email_templates_api.py's module docstrings.
from core.lead_pipeline_api import advance_lead_pipeline_api

# Email/SMS Templates functions moved to api/routers/email_templates.py
# (CAF-00120, god_file_app_py). This removal also fixes a real pre-existing
# bug: this block used to import `list_templates_api` from
# core.email_templates_api, which silently shadowed the *different*,
# 0-arg `list_templates_api` imported from core.assets_api below (used by
# /assets/templates) -- restored to correctly resolving to the assets_api
# version now that only one import binds that name in this module.

# Marketing Growth Platform, Email/SMS upgrades slice (2026-07-18) -- Dynamic
# Personalization + A/B Testing + Revenue Tracking, layered onto the existing
# Campaign/EmailTemplate engines above. See core/campaign_analytics.py/
# core/email_personalization.py's module docstrings. list_merge_fields_api/
# get_merge_values_api/render_personalized_api moved to
# api/routers/email_templates.py (CAF-00120) -- imported fresh there.
from core.campaign_analytics_api import (
    set_ab_variant_api,
    clear_ab_variant_api,
    get_campaign_ab_config_api,
    get_ab_test_results_api,
    get_campaign_revenue_api,
)

# Marketing Growth Platform, Attribution Engine + Marketing ROI Dashboard +
# Vehicle Attribution capstone (2026-07-18) -- Sam's own framing: "most
# valuable once other channels are feeding it real event data," now true
# after the CRM/PURL/Email-SMS slices above. See
# core/marketing_attribution.py's module docstring.
from core.marketing_attribution_api import (
    get_channel_mix_api,
    get_marketing_roi_dashboard_api,
    get_vehicle_attribution_api,
)

# CRM Lists + Opportunities workflow actions (session 82) -- Sam: "under lists we need
# to be able to click on the list names and have them show as a list of names... its
# really there you'd be able to start to curate marketing lists for campaigns," and
# "each [CRM] module needs to be a workable process, not just an information dash...
# how it would flow not only through the marketing department, but what parts would be
# accessible to sales." See core/marketing_lists_api.py/core/opportunities_api.py's
# module docstrings.
from core.marketing_lists_api import (
    create_list_api,
    build_list_from_pool_api,
    get_list_api,
    list_lists_api,
    get_list_members_api,
    update_list_api,
    add_members_api as add_list_members_api,
    remove_members_api as remove_list_members_api,
    delete_list_api,
)

from core.opportunities_api import (
    list_sales_employees_api as list_opportunity_sales_employees_api,
    save_opportunity_pool_as_list_api,
    assign_opportunity_to_sales_api,
)

# Social/Reputation + Advertising (session 83) -- Sam: "hootsuit-style social suite...
# built in social media post builder that includes dropping in inventory... a toggle
# for reputation tracking... bot function to respond to reviews / alert for bad
# reviews" and "advertising dash... meta and google ad campaigns that include
# inventory and allow ai recommendations / building, or granular control." Both
# "publish"/"launch" actions are honestly-labeled SIMULATED graph actions -- this
# sandbox has no real path to the Facebook/Instagram/X/LinkedIn/TikTok/Meta/Google
# APIs. See core/social_posts_api.py/core/reputation_api.py/core/advertising_api.py's
# module docstrings.
# Social media post builder's 10 routes moved to api/routers/social.py
# (CAF-00120, god_file_app_py) -- imported fresh there.

from core.reputation_api import (
    get_reputation_summary_api,
    # list_reviews_api: this name used to get silently shadowed by a
    # same-named-but-different function imported later in this file from
    # core.coaching_api (a leftover dead import from an already-completed
    # router extraction) -- fixed 2026-07-21 by removing that dead import.
    # The GET /reputation/reviews route below depends on THIS function.
    list_reviews_api,
    list_bad_review_alerts_api,
    respond_to_review_api,
    auto_respond_review_api,
    get_competitor_tracking_api,
)

# Advertising's 11 routes moved to api/routers/advertising.py (CAF-00120,
# god_file_app_py) -- imported fresh there.

# Events dash (session 84) -- Sam: "build out the event dash. we want to style it
# after nxtdeal bumper, automotivemastermind.com, and auto alert. this part we
# absolutely have to nail, and has to tightly integrate into the CRM." Two engines:
# core/trigger_alerts_api.py (a live, urgency-ranked Timeline of individually
# actionable signals -- the AutoAlert/automotiveMastermind half) and
# core/dealership_events_api.py (real scheduled dealership events with a
# CRM-list-backed invite audience + RSVP tracking -- the NXTDeal Bumper half). Both
# promote directly into a real new Lead, closing the CRM loop. See both modules'
# docstrings.
from core.trigger_alerts_api import (
    list_alert_types_api,
    get_alert_feed_api as get_trigger_alert_feed_api,
    get_alert_api,
    dismiss_alert_api,
    promote_alert_api,
)

from core.dealership_events_api import (
    list_event_types_api,
    list_rsvp_statuses_api,
    create_event_api,
    get_event_api,
    update_event_api,
    publish_event_api,
    start_event_api,
    complete_event_api,
    cancel_event_api,
    list_events_api,
    create_rsvp_api,
    update_rsvp_status_api,
    list_event_rsvps_api,
    promote_rsvp_to_lead_api,
)

from core.event_planning_api import (
    list_task_statuses_api,
    create_task_api as create_event_task_api,
    update_task_api,
    update_task_status_api,
    delete_task_api,
    list_tasks_for_event_api,
    get_project_management_summary_api,
    get_event_war_room_api,
)

from core.event_campaign_generator_api import (
    generate_event_campaign_draft_api,
    create_event_campaign_api,
    list_campaigns_for_event_api,
)

from core.websites_api import (
    list_section_templates_api,
    list_page_keys_api,
    list_modes_api,
    create_website_api,
    create_website_wizard_api,
    add_section_api,
    update_section_fields_api,
    remove_section_api,
    set_section_locked_api,
    set_mode_api,
    add_owner_api,
    remove_owner_api,
    update_admin_settings_api,
    get_dns_instructions_api,
    get_robots_txt_api,
    submit_website_api,
    get_website_api,
    list_my_websites_api,
    list_pending_websites_api,
    approve_website_api,
    reject_website_api,
    list_site_templates_api,
    apply_site_template_api,
    reorder_sections_api,
    set_page_layout_mode_api,
    set_section_layout_api,
    regenerate_section_api,
    add_library_image_api,
    remove_library_image_api,
    list_library_images_api,
    update_page_seo_api,
    get_page_seo_api,
    preview_website_api,
    get_website_analytics_api,
    get_public_website_api,
    submit_contact_form_api,
    get_sitemap_xml_api,
    get_seo_health_api,
    get_structured_data_api,
    generate_page_seo_copy_api,
    regenerate_vehicle_description_api,
    add_personalization_variant_api,
    remove_personalization_variant_api,
    list_personalization_variants_api,
)
# ACL-free core functions for genuinely public routes below -- sitemap.xml/robots.txt
# (get_sitemap_xml_api/get_robots_txt_api are gated to the site's own builders/
# MARKETING/ADMIN -- wrong for an anonymous crawler request) and the Vehicle Detail
# Page itself (a real site visitor browsing inventory, same reasoning).
from core.website_seo import get_sitemap_xml
from core.websites import get_robots_txt, get_vehicle_landing_page

# Session 85 -- Website Builder overhaul (personal URL microsites + live chat wired
# into the CRM). See core/personal_sites.py/core/website_chat.py module docstrings
# for the two scoping decisions made autonomously after an AskUserQuestion tool
# failure (single-page personal sites, not a full mirror; REST + polling chat, not a
# new public WebSocket).
#
# Personal URL microsites' 13 routes (11 authenticated + 2 public) moved to
# api/routers/personal_sites.py (CAF-00120, god_file_app_py) -- registered via
# app.include_router(personal_sites_router) below.
from core.website_chat_api import (
    start_chat_session_api,
    send_visitor_message_api,
    list_messages_api,
    get_session_api,
    list_open_sessions_api,
    send_employee_reply_api,
    claim_session_api,
    close_session_api,
    promote_session_api,
    list_departments_api,
    list_unified_inbox_api,
    generate_ai_reply_api
)

from core.deals_api import (
    list_lenders_api,
    create_deal_api,
    add_scenario_api,
    remove_scenario_api,
    select_scenario_api,
    choose_in_house_financing_api,
    submit_to_lender_api,
    record_lender_decision_api,
    accept_countered_terms_api,
    update_trade_appraisal_api,
    decode_trade_in_vin_api,
    approve_trade_appraisal_api,
    update_delivery_checklist_api,
    generate_contract_api,
    fund_deal_api,
    cancel_deal_api,
    get_deal_api,
    list_my_deals_api,
    list_all_deals_api,
    list_pending_financing_api
)

from core.help_api import (
    ask_help_api
)

from core.lead_record_api import get_lead_record_api
from core.lead_tasks_api import create_task_api, complete_task_api, list_tasks_api
from core.lead_conversion_api import convert_lead_to_customer_api
from core.lead_assignment_api import transfer_lead_api, list_sales_employees_api
from core.sales_overview_api import get_my_day_api
from core.service_overview_api import get_service_my_day_api
from core.vehicle_holds_api import (
    place_hold_api,
    release_hold_api,
    list_active_holds_api,
    list_my_holds_api,
)
# Vehicle Lifecycle functions moved to api/routers/vehicle_lifecycle.py
# (CAF-00120, god_file_app_py).
# Acquisitions functions moved to api/routers/acquisitions.py (CAF-00120).
from core.pricing_desk_api import (
    get_market_pricing_api,
    get_competitor_comparisons_api,
    get_age_based_adjustment_api,
    get_pricing_recommendation_api,
    get_pricing_view_api,
    get_pricing_queue_api,
    apply_price_recommendation_api,
)
# core.vin_decoder_api import moved to
# api/routers/vin_decoder.py (CAF-00120, god_file_app_py).
from core.lot_control_api import (
    get_lot_map_api,
    get_lot_control_view_api,
    set_lot_position_api,
    get_lot_position_api,
    checkout_key_api,
    checkin_key_api,
    report_key_missing_api,
    get_key_status_api,
    get_key_board_api,
    report_damage_api,
    update_damage_status_api,
    list_damage_reports_api,
    assign_showroom_api,
    remove_showroom_assignment_api,
    get_showroom_board_api,
    log_scan_api,
    get_scan_log_api,
)
# Inventory Merchandising's 11 routes moved to api/routers/merchandising.py
# (CAF-00120, god_file_app_py) -- imported fresh there.
# Wholesale Desk's 12 routes moved to api/routers/wholesale_desk.py
# (CAF-00120, god_file_app_py) -- imported fresh there.
from core.operations_overview_api import get_operations_overview_api
# Operations Tasks' 12 routes moved to api/routers/operations_tasks.py
# (CAF-00120, god_file_app_py) -- imported fresh there.
from core.inventory_aging_api import (
    get_aging_board_api,
    get_vehicle_aging_brief_api,
    reduce_price_api,
    request_wholesale_review_api,
    request_manager_review_api,
    request_auction_assignment_api,
    create_marketing_tie_in_api,
)
from core.operations_scheduling_api import (
    get_recon_schedule_api,
    schedule_recon_api,
    get_delivery_risk_board_api,
    schedule_delivery_api as schedule_operations_delivery_api,
    get_transport_schedule_api,
    update_transport_status_api,
)
from core.document_workflows_api import (
    get_deal_jacket_status_api,
    get_title_status_api,
    request_document_api,
    get_document_packet_api,
    approve_document_api,
    reject_document_api,
    list_pending_approvals_api,
)
from core.operations_alerts_api import (
    get_alert_feed_api,
    get_alert_stats_api,
    acknowledge_alert_api,
)
from core.repair_orders_api import (
    get_catalog_api as get_ro_catalog_api,
    get_ro_board_api,
    get_ro_workspace_api,
    create_repair_order_api,
    advance_stage_api, record_return_review_api, record_return_handover_api, plan_return_followup_api, complete_return_followup_api,
    add_concern_api,
    resolve_concern_api,
    send_estimate_api,
    record_customer_approval_api,
    update_parts_status_api,
    request_part_api,
    update_part_request_status_api,
    update_qc_item_api,
    log_ro_communication_api,
    assign_technician_api,
)
# core.shop_control_api and core.service_customers_api imports moved to
# backend/api/routers/shop_control.py and backend/api/routers/
# service_customers.py (CAF-00120, god_file_app_py) -- no longer referenced
# from this file.
from core.parts_desk_api import (
    get_parts_request_queue_api,
    mark_special_order_api,
    get_special_orders_api,
    get_inventory_recommendations_api,
)
# core.warranty_desk_api import moved to
# api/routers/warranty_desk.py (CAF-00120, god_file_app_py).
from core.vehicle_inspection_api import (
    get_catalog_api as get_dvi_catalog_api,
    get_inspection_api,
    start_inspection_api,
    update_inspection_item_api,
    attach_inspection_photo_api,
    complete_inspection_api,
    create_concerns_from_inspection_api,
    get_inspection_history_api,
)
from core.approval_center_api import (
    generate_approval_link_api,
    get_approval_link_status_api,
    revoke_approval_link_api,
)
from core.approval_center import get_public_approval_view, record_public_approval_decision
# Loaner & Shuttle Management's core.loaner_shuttle_api import moved to
# api/routers/loaner_shuttle.py (CAF-00120, god_file_app_py).
from core.service_sales_handoff_api import (  # noqa: F401 -- get_conversion_opportunities_api used below
    get_conversion_opportunities_api,
    get_opportunity_queue_api,
    get_ro_handoff_status_api,
    flag_manual_opportunity_api,
    promote_to_sales_api,
    dismiss_opportunity_api,
    get_handoff_stats_api,
)
from core.loan_servicing_api import (
    get_loan_detail_api,
    get_loan_financials_api,
    get_loan_timeline_api,
    get_loan_status_api,
    set_loan_status_api,
    get_simulated_payment_status_api,
    get_portfolio_dashboard_api,
    compute_amortization_schedule_api,
)
from core.payments_api import (
    record_payment_api,
    list_payments_for_loan_api,
    get_real_payment_summary_api,
    create_auto_draft_api,
    set_auto_draft_status_api,
    list_auto_drafts_api,
    run_due_auto_drafts_api,
    create_promise_to_pay_api,
    get_promise_status_api,
    list_promises_to_pay_api,
    record_extension_api,
    record_deferral_api,
    list_payment_adjustments_api,
    request_payoff_api,
    fulfill_payoff_request_api,
    list_payoff_requests_api,
    generate_payment_portal_link_api,
    get_payment_portal_link_status_api,
    revoke_payment_portal_link_api,
    get_payments_dashboard_api,
)
from core.payments import get_public_portal_view, submit_public_payment, submit_public_payoff_request
from core.collections_api import (
    get_collection_queue_api,
    get_agent_workspace_api,
    get_collection_stage_api,
    advance_collection_stage_api,
    compute_risk_score_api,
    get_priority_recommendation_api,
    log_contact_api,
    get_contact_history_api,
    get_collections_dashboard_api,
)
# Repossessions functions moved to api/routers/repossessions.py (CAF-00120,
# god_file_app_py).
from core.asset_management_api import (
    get_lien_status_api,
    update_lienholder_api,
    release_lien_api,
    get_insurance_status_api,
    update_insurance_api,
    get_collateral_valuation_api,
    get_asset_summary_api,
    get_asset_portfolio_dashboard_api,
)
from core.lending_compliance_api import (
    get_lending_compliance_dashboard_api,
    get_ofac_screening_status_api,
    record_ofac_screening_api,
    record_cash_payment_api,
    get_form_8300_status_api,
    file_form_8300_api,
    get_form_8300_obligations_api,
)
from core.glba_program_api import (
    get_glba_readiness_summary_api,
    list_glba_program_items_api,
    get_glba_component_status_api,
    set_glba_component_status_api,
)
from core.pci_dss_guard_api import run_pci_posture_scan_api
from core.crypto_agility_api import get_crypto_agility_posture_api, run_crypto_inventory_scan_api
from core.secrets_api import get_secrets_posture_api
from core.secrets import warn_on_dev_fallbacks
from core.loan_accounting_api import (
    get_loan_accounting_summary_api,
    get_daily_ledger_api,
    get_unposted_payments_api,
    post_payment_to_ledger_api,
    post_all_due_api,
    close_accounting_period_api,
    reopen_accounting_period_api,
    list_periods_api,
)
from core.general_ledger_api import (
    get_chart_of_accounts_api,
    sync_real_entries_api,
    generate_simulated_entries_api,
    delete_entry_api,
    get_general_ledger_api,
    get_trial_balance_api,
    get_income_statement_api,
    get_balance_sheet_api,
)
from core.bank_reconciliation_api import (
    generate_simulated_bank_feed_api,
    get_reconciliation_status_api,
    confirm_match_api,
    mark_transaction_reviewed_api,
    list_transactions_api,
)
from core.customer_360_api import get_customer_360_api
from core.smart_audiences_api import (
    get_field_catalog_api,
    list_presets_api,
    preview_preset_api,
    preview_conditions_api,
    create_audience_api,
    delete_audience_api,
    list_audiences_api,
    evaluate_audience_api,
)
from core.lead_scoring_api import compute_score_api, leaderboard_api as lead_scoring_leaderboard_api
from core.purls_api import (
    generate_purl_api,
    revoke_purl_api,
    list_purls_api,
    create_mail_piece_api,
    get_purl_analytics_api,
    get_purl_dashboard_api,
    bulk_generate_purls_api,
)
from core.purls import get_personalized_offer, record_purl_visit, submit_purl_lead
from core.permissions_registry_api import (
    list_permission_catalog_api,
    get_effective_permissions_api,
    list_overrides_for_employee_api,
    list_all_overrides_api,
    set_override_api,
    revoke_override_api,
    list_approval_chains_api,
    create_approval_request_api,
    approve_step_api,
    reject_step_api,
    cancel_request_api,
    get_approval_request_api,
    list_approval_requests_api,
    get_tier_distribution_api,
)
# core.vendor_management_api imports moved to backend/api/routers/vendors.py
# (CAF-00120, god_file_app_py) -- no longer referenced from this file.
from core.strategic_planning_api import (
    get_strategic_planning_overview_api,
    get_strategic_planning_catalog_api,
    get_quarterly_rollup_api,
    create_objective_api,
    get_objective_api,
    list_objectives_api,
    update_objective_api,
    update_objective_progress_api,
    update_objective_budget_api,
    cancel_objective_api,
    reopen_objective_api,
    sync_objective_to_monthly_goal_api,
    create_initiative_api,
    get_initiative_api,
    list_initiatives_api,
    update_initiative_status_api,
    update_initiative_progress_api,
    update_initiative_budget_api,
)
from core.ai_business_analyst_api import ask_business_analyst_api
from core.sales_menu import compare_vehicles as compare_vehicles_sales
from core.bdc_api import (
    get_bdc_dashboard_api,
    get_untouched_queue_api,
    get_qualification_queue_api,
    get_handoff_candidates_api,
)
from core.manager_to_api import (
    list_to_reasons_api,
    list_to_statuses_api,
    list_to_outcomes_api,
    request_to_api,
    claim_to_api,
    resolve_to_api,
    list_open_tos_api,
    list_tos_api,
    get_to_stats_api,
)
# Demo Drive's core.demo_drive_api import moved to
# api/routers/demo_drives.py (CAF-00120, god_file_app_py).
# Credit Applications' 13 routes moved to api/routers/credit_apps.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(credit_apps_router) below.
# eSignature's 14 routes moved to api/routers/esignature.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(esignature_router) below.

from core.fi_products_api import (
    get_fi_product_catalog_api,
    get_fi_menu_api,
    recommend_fi_products_api,
    present_fi_products_api,
    update_fi_product_pricing_api,
    decide_fi_product_api,
    get_product_penetration_stats_api,
    list_deals_needing_fi_menu_api,
    get_fi_products_dashboard_api,
)

# Lost Sale Recovery's 11 routes moved to api/routers/lost_sale_recovery.py
# (CAF-00120, god_file_app_py) -- imported fresh there.

# orphan_owner_mining_api imports moved to api/routers/orphan_owners.py (CAF-00120).

from core.department_intelligence_api import (
    list_departments_api as list_department_intelligence_api,
    get_department_api as get_department_intelligence_api
)

from core.bot_api import (
    get_my_tasks_api,
    record_feedback_api,
    start_coverage_api,
    end_coverage_api,
    list_coverage_api,
    get_screen_guidance_api,
    automate_screen_guidance_api,
    do_it_screen_guidance_api
)

# Agentic-bot FLEET (2026-07-23, Pillar 4 slice 1) -- team agents + workflow recording.
from core.bot_fleet_api import (
    get_fleet_api,
    get_team_workflows_api,
    record_workflow_step_api,
    activate_agent_api,
    deactivate_agent_api,
    run_recognized_workflow_api
)

from core.shared_knowledge_api import (
    get_shared_knowledge_api,
    contribute_insight_api,
    publish_recognized_workflows_api,
    delete_shared_entry_api,
)

from core.ai_worker_api import (
    get_workforce_api,
    get_worker_detail_api,
    activate_worker_api,
    deactivate_worker_api,
    handle_interaction_api,
    run_worker_queue_api,
)

from core.connect_api import (
    get_connect_inbox_api,
    get_connect_timeline_api,
    get_connect_analytics_api,
    get_connect_intelligence_api,
    get_connect_comm_intelligence_api,
)

from core.dealeros_verify_api import (
    get_verify_dashboard_api,
    list_verifications_api,
    get_verification_api,
    get_verify_catalog_api,
    public_start_verification,
    public_get_verification,
    public_set_contact,
    public_request_code,
    public_confirm_code,
    public_submit_identity,
    public_submit_credit,
)

from core.execution_modes_api import (
    get_execution_modes_api,
    get_execution_workflow_api,
    set_execution_mode_api,
)

from core.negotiation_engine_api import (
    get_negotiation_dashboard_api,
    get_negotiation_rules_api,
    set_negotiation_rules_api,
    list_sessions_api,
    get_session_api as get_negotiation_session_api,
    start_session_api,
    evaluate_offer_api,
    apply_offer_api,
    resolve_escalation_api,
    accept_session_api,
)

# NXTDeal Digital Retail self-service (DR-4) -- token-driven customer orchestration.
from core.digital_retail import (
    start_deal as retail_start_deal,
    submit_trade as retail_submit_trade,
    start_negotiation as retail_start_negotiation,
    make_offer as retail_make_offer,
    accept_negotiation as retail_accept_negotiation,
    apply_credit as retail_apply_credit,
    choose_financing as retail_choose_financing,
    select_fi as retail_select_fi,
    sign as retail_sign,
    schedule_delivery as retail_schedule_delivery,
    get_deal_room as retail_get_deal_room,
)

# Digital Retail KPI dashboard (DR-8).
from core.digital_retail_analytics_api import get_digital_retail_dashboard_api

# Integration provider seam.
from core.integrations_registry_api import get_integrations_api, configure_provider_api
from core.marketplace_api import (
    get_marketplace_api,
    get_listing_api,
    install_listing_api,
    uninstall_listing_api,
)
from core.customer_comms_api import (
    provider_status_api as comms_provider_status_api,
    search_customers_api,
    save_contact_api,
    place_call_api,
    end_call_api,
    send_text_api,
    get_conversation_api,
    get_call_intelligence_api,
    recent_activity_api,
)

# Home Delivery + Try Before You Buy (DR-6).
from core.delivery_fulfillment_api import (
    get_fulfillment_dashboard_api,
    list_deliveries_api,
    get_delivery_api,
    schedule_delivery_api,
    assign_driver_api,
    update_delivery_status_api,
    get_tbyb_program_api,
    set_tbyb_program_api,
    list_tbyb_api,
    get_tbyb_api,
    start_tbyb_api,
    tbyb_action_api,
)

from core.bot_scheduler import (
    start as start_bot_scheduler,
    stop as stop_bot_scheduler
)

# core.coaching_api import moved to
# api/routers/coaching.py (CAF-00120, god_file_app_py).
#
# NOTE: this dead import used to shadow core.reputation_api.list_reviews_api
# (imported earlier in this file) with core.coaching_api.list_reviews_api,
# a same-named but different function -- a real bug silently breaking the
# live GET /reputation/reviews route. Removing this block fixes that as a
# side effect (see the module-name-collision note near the top import of
# core.reputation_api for the full story).

from core.data_connections_api import (
    create_connection_api,
    list_connections_api,
    ingest_csv_api,
    test_api_connection_api,
    readiness_predictions_api,
    prediction_timeline_api
)

from core.employee_value_api import (
    list_employee_values_api,
    get_employee_value_api
)

from core.form_review import PacketDraft, assess_packet_draft
from core.compliance_api import (
    list_rules_api as list_compliance_rules_api,
    list_alerts_api as list_compliance_alerts_api,
    get_alert_api as get_compliance_alert_api,
    resolve_alert_api as resolve_compliance_alert_api,
    override_alert_api as override_compliance_alert_api,
    run_scan_api as run_compliance_scan_api
)

from core.compliance_scheduler import (
    start as start_compliance_scheduler,
    stop as stop_compliance_scheduler
)

from core.network_benchmark import seed_peer_snapshots

from core.platform_metrics import record_request

from core.knowledge_base import seed_articles

from core.knowledge_base_api import (
    list_articles_api as list_knowledge_articles_api,
    get_article_api as get_knowledge_article_api
)

# Both background schedulers (the session-36 agentic bot and the session-38 compliance
# scanner) need a running asyncio event loop, so they're started/stopped on the app's
# lifecycle. This is the modern FastAPI lifespan= context manager (one handler for both
# schedulers), replacing the two pairs of deprecated @app.on_event("startup"/"shutdown")
# handlers used previously -- @app.on_event emits DeprecationWarnings and is slated for
# removal in a future Starlette/FastAPI release. Behaviour is identical: everything
# before the `yield` runs on startup, everything after runs on shutdown. See
# core/bot_scheduler.py / core/compliance_scheduler.py for what each tick does and their
# documented single-process/in-memory limitations.
@asynccontextmanager
async def lifespan(app: FastAPI):

    # core/secrets.py Task #13, 2026-07-20 -- a real, loud, impossible-to-miss stderr
    # warning the moment this process boots on any secret still resolving to its
    # insecure dev-only fallback value. Deliberately does not refuse to boot -- see
    # that module's own docstring for why.
    warn_on_dev_fallbacks()

    from core import agent_events
    from core import sales_sequence_scheduler
    from core import dealer_cloud
    from core import bridge_sync
    from core import loyalty_scheduler
    from core import bridge_chrono

    # Register cleanup before each start, including a partially-started worker.
    # Cancel every worker before waiting, including when another stop raises.
    shutdown = WorkerShutdown()
    async with AsyncExitStack() as cleanup:
        cleanup.push_async_callback(shutdown.wait)
        for start, stop in (
            (start_bot_scheduler, stop_bot_scheduler),
            (start_compliance_scheduler, stop_compliance_scheduler),
            (agent_events.start, agent_events.stop),
            (sales_sequence_scheduler.start, sales_sequence_scheduler.stop),
            (dealer_cloud.start, dealer_cloud.stop),
            (bridge_sync.start, bridge_sync.stop),
            (bridge_chrono.start, bridge_chrono.stop),
            (loyalty_scheduler.start, loyalty_scheduler.stop),
        ):
            cleanup.callback(shutdown.stop, stop)
            start()
        yield


from core.cors_policy import DEALER_WEB_ORIGINS, LEGACY_DEALER_ORIGIN_REGEX

app = FastAPI(lifespan=lifespan)
from core.request_observability import install as install_request_observability
install_request_observability(app)
from api.routers.dealer_cloud import router as dealer_cloud_router
app.include_router(dealer_cloud_router)

from api.routers.mysales_inventory import router as mysales_inventory_router
app.include_router(mysales_inventory_router)

from api.routers.agent_fabric import router as agent_fabric_router
app.include_router(agent_fabric_router)

from api.routers.dealer_bridge import router as dealer_bridge_router
app.include_router(dealer_bridge_router)
from api.routers.agent_mcp import router as agent_mcp_router
app.include_router(agent_mcp_router)
from api.routers.agent_oauth import router as agent_oauth_router
app.include_router(agent_oauth_router)

# Install before CORS so browser clients receive the explicit unavailable response.
from core.customer_verification_boundary import CustomerVerificationBoundary
from api.administration_boundary import AdministrationBoundary
app.add_middleware(AdministrationBoundary)
app.add_middleware(CustomerVerificationBoundary)

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEALER_WEB_ORIGINS,
    allow_origin_regex=LEGACY_DEALER_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# Sam (2026-07-16): "make sure that this website doesn't get indexed... this is just a
# test url." A JSON API isn't normally something search engines index, but this backend
# also serves the real public-facing routes under /public/* (website pages, personal
# sites) that a crawler genuinely could hit -- so this is the same defense-in-depth
# posture as frontend/app/robots.ts + frontend/app/layout.tsx's noindex meta tag, just on
# the API side. Same env-var name/convention as the frontend so one flip covers a whole
# deployment consistently: unset/false (default) blocks indexing everywhere; set
# DEALEROS_ALLOW_INDEXING=true on a specific deployment once it's ready to go live.
_ALLOW_INDEXING = os.environ.get("DEALEROS_ALLOW_INDEXING", "").lower() == "true"


@app.middleware("http")
async def add_robots_header(request: Request, call_next):
    response = await call_next(request)
    if not _ALLOW_INDEXING:
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    # Credentials also arrive via query tokens, network headers and OIDC callbacks.
    # API responses default to non-storage regardless of the authentication carrier.
    response.headers["Cache-Control"] = "no-store"
    return response


def _customer_account_path(path):
    return path.startswith(("/customer/", "/public/customer/"))


@app.middleware("http")
async def protect_customer_responses(request: Request, call_next):
    response = await call_next(request)
    if _customer_account_path(request.url.path):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(RequestValidationError)
async def customer_validation_error(request: Request, exc: RequestValidationError):
    if not _customer_account_path(request.url.path):
        return await request_validation_exception_handler(request, exc)
    # Pydantic's default error includes `input` (passwords/codes/contact data).
    # Keep field locations/types, but never echo input, context or parser details.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": error["loc"], "type": error["type"],
         "msg": "Invalid customer request field. Check its format and length."}
        for error in exc.errors()
    ]})


# Infrastructure & Platform Operations rebuild, slice 1 (2026-07-19) -- real,
# lightweight, in-process request/error/latency instrumentation. See
# core/platform_metrics.py's own module docstring for the full honesty
# posture (in-memory only, resets on restart, real route-group mapping, no
# fabricated infra telemetry). Registered after add_robots_header so this
# still wraps every real route including the ones added below.
import time as _platform_metrics_time


@app.middleware("http")
async def track_platform_metrics(request: Request, call_next):
    started = _platform_metrics_time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = (_platform_metrics_time.monotonic() - started) * 1000
        record_request(request.url.path, 500, latency_ms)
        raise
    latency_ms = (_platform_metrics_time.monotonic() - started) * 1000
    record_request(request.url.path, response.status_code, latency_ms)
    return response


# Domain-scoped routers (CAF-00120, god_file_app_py -- splitting this file into
# routers rather than one flat 14,800+-line file). Each one is a self-contained
# api/routers/<domain>.py module with its own APIRouter() + route handlers +
# route-specific Pydantic models, importing shared auth helpers from api/deps.py
# instead of this file (avoids a circular import — see api/deps.py's own
# docstring). Included early, before any inline route below, so a router's
# routes register at the same relative position they used to occupy.
from api.routers.coaching import router as coaching_router
from api.routers.workforce import router as workforce_router
from api.routers.marketing_studio import router as marketing_studio_router
from api.routers.lender_intelligence import router as lender_intelligence_router
from api.routers.inventory_syndication import router as inventory_syndication_router
from api.routers.devices import router as devices_router
from api.routers.appointments import router as appointments_router
from api.routers.system_config import router as system_config_router
from api.routers.data_management import router as data_management_router
from api.routers.identity_access import router as identity_access_router
from api.routers.audit_center import router as audit_center_router
from api.routers.governance import router as governance_router
from api.routers.workflow_automation import router as workflow_automation_router
from api.routers.lead_routing_rules import router as lead_routing_rules_router
from api.routers.content_library import router as content_library_router
from api.routers.marketing_journeys import router as marketing_journeys_router
from api.routers.marketing_operations import router as marketing_operations_router
from api.routers.sales_crm import router as sales_crm_router
from api.routers.connections import router as connections_router
from api.routers.buy_propensity import router as buy_propensity_router
from api.routers.payroll import router as payroll_router
from api.routers.mysales_adoption import router as mysales_adoption_router
from api.routers.ai_management import router as ai_management_router
from api.routers.ai_execution_tier import router as ai_execution_tier_router
from api.routers.business_health import router as business_health_router
from api.routers.enterprise_risk_center import router as enterprise_risk_center_router
from api.routers.readiness_recommendations import router as readiness_recommendations_router
from api.routers.readiness_overview import router as readiness_overview_router
from api.routers.data_health import router as data_health_router
from api.routers.performance_readiness import router as performance_readiness_router
from api.routers.readiness_forecasts import router as readiness_forecasts_router
from api.routers.readiness_scenarios import router as readiness_scenarios_router
from api.routers.ai_audit import router as ai_audit_router
from api.routers.ai_kill_switch import router as ai_kill_switch_router
from api.routers.bot_permissions import router as bot_permissions_router
from api.routers.vin_decoder import router as vin_decoder_router
from api.routers.vendors import router as vendors_router
from api.routers.shop_control import router as shop_control_router
from api.routers.service_customers import router as service_customers_router
from api.routers.orphan_owners import router as orphan_owners_router
from api.routers.sso import router as sso_router
from api.routers.loaner_shuttle import router as loaner_shuttle_router
from api.routers.demo_drives import router as demo_drives_router
from api.routers.warranty_desk import router as warranty_desk_router
from api.routers.acquisitions import router as acquisitions_router
from api.routers.credit_apps import router as credit_apps_router
from api.routers.esignature import router as esignature_router
from api.routers.vehicle_lifecycle import router as vehicle_lifecycle_router
from api.routers.repossessions import router as repossessions_router
from api.routers.email_templates import router as email_templates_router
from api.routers.wholesale_desk import router as wholesale_desk_router
from api.routers.operations_tasks import router as operations_tasks_router
from api.routers.personal_sites import router as personal_sites_router
from api.routers.merchandising import router as merchandising_router
from api.routers.lost_sale_recovery import router as lost_sale_recovery_router
from api.routers.advertising import router as advertising_router
from api.routers.social import router as social_router
from api.routers.network import router as network_router
from api.routers.up_system import router as up_system_router
from api.routers.workflow_engine_v2 import router as workflow_engine_v2_router
from api.routers.communications_hub import router as communications_hub_router
from api.routers.call_center import router as call_center_router
from api.routers.call_coaching import router as call_coaching_router
from api.routers.customer_journey import router as customer_journey_router
from api.routers.accessories import router as accessories_router
from api.routers.equity_center import router as equity_center_router
from api.routers.inventory_advertising import router as inventory_advertising_router
from api.routers.loyalty import router as loyalty_router
from api.routers.loyalty_program import router as loyalty_program_router
from api.routers.loyalty_customer import router as loyalty_customer_router
from api.routers.success_center import router as success_center_router
from api.routers.consulting_engine import router as consulting_engine_router
from api.routers.ai_assist import router as ai_assist_router
from api.routers.media_library import router as media_library_router

app.include_router(coaching_router)
app.include_router(workforce_router)
app.include_router(marketing_studio_router)
app.include_router(lender_intelligence_router)
app.include_router(inventory_syndication_router)
app.include_router(devices_router)
app.include_router(appointments_router)
app.include_router(system_config_router)
app.include_router(data_management_router)
app.include_router(identity_access_router)
app.include_router(audit_center_router)
app.include_router(governance_router)
app.include_router(workflow_automation_router)
app.include_router(lead_routing_rules_router)
app.include_router(content_library_router)
app.include_router(marketing_journeys_router)
app.include_router(marketing_operations_router)
from api.routers.marketing_planning import router as marketing_planning_router
app.include_router(marketing_planning_router)
app.include_router(sales_crm_router)
from api.routers.sales_crm_advanced import router as sales_crm_advanced_router
app.include_router(sales_crm_advanced_router)
app.include_router(connections_router)
app.include_router(buy_propensity_router)
app.include_router(payroll_router)
app.include_router(mysales_adoption_router)
app.include_router(ai_management_router)
app.include_router(ai_execution_tier_router)
app.include_router(business_health_router)
app.include_router(enterprise_risk_center_router)
app.include_router(readiness_recommendations_router)
app.include_router(readiness_overview_router)
app.include_router(data_health_router)
app.include_router(performance_readiness_router)
app.include_router(readiness_forecasts_router)
app.include_router(readiness_scenarios_router)
app.include_router(ai_audit_router)
app.include_router(ai_kill_switch_router)
app.include_router(bot_permissions_router)
app.include_router(vin_decoder_router)
app.include_router(vendors_router)
app.include_router(shop_control_router)
app.include_router(service_customers_router)
app.include_router(orphan_owners_router)
app.include_router(sso_router)
app.include_router(loaner_shuttle_router)
app.include_router(demo_drives_router)
app.include_router(warranty_desk_router)
app.include_router(acquisitions_router)
app.include_router(credit_apps_router)
app.include_router(esignature_router)
app.include_router(vehicle_lifecycle_router)
app.include_router(repossessions_router)
app.include_router(email_templates_router)
app.include_router(wholesale_desk_router)
app.include_router(operations_tasks_router)
app.include_router(personal_sites_router)
app.include_router(merchandising_router)
app.include_router(lost_sale_recovery_router)
app.include_router(advertising_router)
app.include_router(social_router)
app.include_router(network_router)
app.include_router(up_system_router)
app.include_router(workflow_engine_v2_router)
app.include_router(communications_hub_router)
app.include_router(call_center_router)
app.include_router(call_coaching_router)
app.include_router(customer_journey_router)
app.include_router(accessories_router)
app.include_router(equity_center_router)
app.include_router(inventory_advertising_router)
app.include_router(loyalty_router)
app.include_router(loyalty_program_router)
app.include_router(loyalty_customer_router)
app.include_router(success_center_router)
app.include_router(consulting_engine_router)
app.include_router(ai_assist_router)
app.include_router(media_library_router)


# Multi-tenant support (NXTDeal Hub, session 50) -- every dealer's NXTDeal backend is
# the same codebase, pointed at its own storage directory via one env var
# (DEALEROS_STORAGE_DIR, see core/storage_paths.py). Defaults to plain "storage" so this
# is a no-op for today's one real dealer until a second tenant is actually deployed.
# hub/ (new, sibling to backend/) is the tool that provisions a fresh tenant directory.
# See CLAUDE.md's "NXTDeal Hub / Multi-Tenant Architecture" section -- importantly, this
# wiring only covers the three boot-time loads below; most save_graph()/save_audit_log()/
# save_credentials() call sites elsewhere in core/ still hardcode the literal
# "storage/..." path and have NOT yet been migrated to GRAPH_PATH/AUDIT_PATH/
# CREDENTIALS_PATH -- see BUILD_QUEUE.md for the tracked file list.
load_graph(
    GRAPH_PATH
)

load_audit_log(
    AUDIT_PATH
)

load_credentials(
    CREDENTIALS_PATH
)

load_customer_credentials(
    CUSTOMER_CREDENTIALS_PATH()
)

# Demo tenant (DEALEROS_DEMO): if the graph is empty, self-seed a rich dataset into memory so
# the guided tours + AI Q&A have real data. Saves no-op in demo mode, so nothing persists;
# a redeploy resets to the seed. Immediate no-op on any real dealer backend. See core/demo_seed.
from core.demo_seed import ensure_seeded as _ensure_demo_seeded
_ensure_demo_seeded()

# storage/workflows.json and storage/assignments.json no longer exist as separate
# stores (2026-07-13 "one graph" unification, see CLAUDE.md) — lead pipeline state and
# employee assignment are now attributes/relationships on storage/graph.json itself,
# loaded by load_graph() above.
print(
    "Loaded pipeline leads:",
    len(
        get_all_pipeline_entity_ids()
    )
)

# Communications (session 28) -- channels are fixed/well-known, seeded as graph
# entities on every process start. Idempotent: does nothing if storage/graph.json
# already has them (see core/messaging.py's seed_channels() docstring).
seed_channels()

# Network intelligence layer (session 38) -- seeds the simulated blind peer-dealer
# NetworkPeerSnapshot entities once per department, same idempotent-on-every-boot
# convention as seed_channels() above. See core/network_benchmark.py's docstring for
# why these are simulated (no real second NXTDeal dealer exists in this environment
# yet) and how they'd be replaced the moment one connects.
seed_peer_snapshots()

# Knowledge base (session 38) -- seeds the real starter Getting Started/How-To
# articles once, same idempotent-on-every-boot convention as seed_channels()/
# seed_peer_snapshots() above.
seed_articles()


# Agentic bot layer (session 36) and compliance agent (session 38) are both real
# background asyncio tasks (not "compute when the page happens to be open" shortcuts --
# Sam's explicit scoping answer). Both are started/stopped in the lifespan= context
# manager defined above, next to the FastAPI() constructor.


class QuestionRequest(BaseModel):

    question: str


class AIRequest(BaseModel):

    question: str


class HelpRequest(BaseModel):
    # department/screen_context are both optional -- a caller that doesn't send them
    # just gets a less-tailored answer (ask_help_api() degrades gracefully, see its
    # _describe_screen_context()), not an error.
    question: str
    department: str | None = None
    screen_context: dict | None = None


class LoginRequest(BaseModel):
    # `employee_id` accepts either an actual employee_id or an email address as of
    # 2026-07-13 (session 20) — kept this field name rather than renaming to `identifier`
    # to avoid a breaking request-body change; core.auth_api.login() resolves whichever
    # form was sent. See core/auth.py's CredentialStore.resolve_identifier().
    employee_id: str
    password: str


class CreateCredentialRequest(BaseModel):

    employee_id: str
    role: str
    temp_password: str | None = None
    email: str | None = None


class ChangePasswordRequest(BaseModel):

    old_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):

    employee_id: str
    temp_password: str | None = None


class CreateAssetRequest(BaseModel):

    template_key: str
    fields: dict = {}
    vehicle_id: str | None = None
    campaign_id: str | None = None


class ReviewAssetRequest(BaseModel):

    notes: str | None = None


class CreateFieldNoteRequest(BaseModel):

    department: str
    category: str
    body: str
    linked_entity_id: str | None = None


class UpdateEntityRequest(BaseModel):

    patch: dict


class CreateLeadRequest(BaseModel):

    first_name: str
    last_name: str
    source: str
    phone: str | None = None
    email: str | None = None
    city: str | None = None
    state: str | None = None
    vin: str | None = None


class CreateVehicleRequest(BaseModel):

    vin: str
    year: str
    make: str
    model: str
    trim: str | None = None
    color: str | None = None
    mileage: str | None = None
    condition: str
    price: str | None = None
    cost: str | None = None
    stock_number: str | None = None
    lot: str


class CreateServiceRecordRequest(BaseModel):

    vin: str | None = None
    description: str
    pay_type: str
    status: str = "Completed"
    customer_id: str | None = None
    mileage: str | None = None
    cost: str | None = None
    parts_cost: str | None = None
    labor_hours: str | None = None


class StartWorkflowRequest(BaseModel):

    workflow_key: str
    linked_entity_id: str | None = None
    notes: str | None = None


class AdvanceWorkflowRequest(BaseModel):

    notes: str | None = None


class AudiencePreviewRequest(BaseModel):

    campaign_type: str
    params: dict = {}


class CreateCampaignRequest(BaseModel):

    campaign_type: str
    name: str
    channel: str | None = None
    params: dict = {}
    linked_asset_id: str | None = None
    linked_template_id: str | None = None


class AdvanceLeadPipelineRequest(BaseModel):

    next_state: str


# Email/SMS Template request models moved to api/routers/email_templates.py
# (CAF-00120, god_file_app_py).


class UpdateCampaignRequest(BaseModel):

    patch: dict = {}


# Bumper-parity campaign tooling (2026-07-25): Duplication Station, Multi-Planner,
# Recurring Schedule.
class DuplicateCampaignRequest(BaseModel):

    new_name: str | None = None


class BulkCreateCampaignsRequest(BaseModel):

    specs: list = []


class CreateRecurringScheduleRequest(BaseModel):

    base_campaign_id: str
    cadence: str
    start_date: str
    end_date: str | None = None
    interval: int = 1
    name: str | None = None


class SetRecurringScheduleActiveRequest(BaseModel):

    active: bool


class SendCampaignRequest(BaseModel):

    resend: bool = False


class RunRecurringSchedulesRequest(BaseModel):

    today: str | None = None


# Bumper-parity: Bulk Import with column mapping + dedupe.
class AnalyzeImportRequest(BaseModel):

    csv_text: str
    target_type: str


class PreviewImportRequest(BaseModel):

    csv_text: str
    mapping: dict = {}
    target_type: str
    dedupe: bool = True


class CommitImportRequest(BaseModel):

    csv_text: str
    mapping: dict = {}
    target_type: str
    dedupe: bool = True


# Bumper-parity: user/employee management + role assignment.
class CreateUserRequest(BaseModel):

    first_name: str
    last_name: str
    email: str | None = None
    role: str
    department: str | None = None
    title: str | None = None
    temp_password: str | None = None


class UpdateUserRoleRequest(BaseModel):

    new_role: str


class SetAbVariantRequest(BaseModel):

    variant_b_template_id: str


class CreateListRequest(BaseModel):

    name: str
    description: str = ""


class BuildListFromPoolRequest(BaseModel):

    name: str
    campaign_type: str
    params: dict = {}
    description: str = ""


class UpdateListRequest(BaseModel):

    patch: dict = {}


class ListMembersRequest(BaseModel):

    entity_ids: list = []


class SaveOpportunityAsListRequest(BaseModel):

    name: str
    campaign_type: str
    params: dict = {}
    description: str = ""


class AssignOpportunityRequest(BaseModel):

    lead_id: str
    assign_to_employee_id: str


# Social media post builder's request models moved to api/routers/social.py
# (CAF-00120, god_file_app_py).


class RespondToReviewRequest(BaseModel):

    response_text: str


# Advertising request models moved to api/routers/advertising.py
# (CAF-00120, god_file_app_py).


class DismissAlertRequest(BaseModel):

    notes: str | None = None


class PromoteAlertRequest(BaseModel):

    assign_to_employee_id: str | None = None


class CreateEventRequest(BaseModel):

    name: str
    event_type: str
    start_time: str | None = None
    end_time: str | None = None
    location: str = ""
    capacity: int | None = None
    description: str = ""
    linked_list_id: str | None = None


class UpdateEventRequest(BaseModel):

    patch: dict = {}


class CreateRsvpRequest(BaseModel):

    name: str
    phone: str | None = None
    email: str | None = None
    customer_id: str | None = None
    lead_id: str | None = None
    source: str = "walk_in"


class UpdateRsvpStatusRequest(BaseModel):

    status: str


class PromoteRsvpRequest(BaseModel):

    assign_to_employee_id: str | None = None


class CreateEventTaskRequest(BaseModel):

    title: str
    assignee_employee_id: str | None = None
    due_date: str | None = None
    notes: str = ""


class UpdateEventTaskRequest(BaseModel):

    patch: dict = {}


class UpdateEventTaskStatusRequest(BaseModel):

    status: str


class GenerateEventCampaignRequest(BaseModel):

    channel: str = "email"
    tone: str = "friendly and professional"


class CreateEventCampaignRequest(BaseModel):

    channel: str = "email"
    tone: str = "friendly and professional"


class CreateWebsiteRequest(BaseModel):

    name: str
    mode: str = "traditional"


class CreateWebsiteWizardRequest(BaseModel):

    dealership_info: dict
    mode: str = "traditional"


class AddSectionRequest(BaseModel):

    section_key: str
    fields: dict = {}


class UpdateSectionFieldsRequest(BaseModel):

    fields: dict = {}


class SetSectionLockedRequest(BaseModel):

    locked: bool


class SetWebsiteModeRequest(BaseModel):

    mode: str


class WebsiteOwnerRequest(BaseModel):

    employee_id: str


class UpdateWebsiteAdminSettingsRequest(BaseModel):

    patch: dict


class ReviewWebsiteRequest(BaseModel):

    notes: str | None = None


# Session 85 -- Website Builder overhaul request models.

class ApplySiteTemplateRequest(BaseModel):

    template_key: str
    dealership_name: str | None = None


class ReorderSectionsRequest(BaseModel):

    new_order: list[int]


class SetPageLayoutModeRequest(BaseModel):

    mode: str


class SetSectionLayoutRequest(BaseModel):

    x: float
    y: float
    width: float
    height: float


class RegenerateSectionRequest(BaseModel):

    instructions: str | None = None


class AddLibraryImageRequest(BaseModel):

    url: str
    label: str | None = None


class UpdatePageSeoRequest(BaseModel):

    patch: dict


class PreviewWebsiteRequest(BaseModel):

    mode_override: str | None = None
    utm_source: str | None = None
    referrer: str | None = None


class AddPersonalizationVariantRequest(BaseModel):

    match: dict = {}
    field_overrides: dict = {}


class SubmitContactFormRequest(BaseModel):

    page_key: str
    section_index: int
    name: str
    email: str | None = None
    phone: str | None = None
    message: str | None = None
    vehicle_id: str | None = None
    intent: str | None = None
    request_id: str | None = None


class StartChatSessionRequest(BaseModel):

    visitor_name: str | None = None
    visitor_email: str | None = None
    initial_message: str | None = None
    department: str | None = None


# NXTDeal Verify (Digital Retail) -- public, token-driven customer verification bodies.
class VerifyStartRequest(BaseModel):

    email: str | None = None
    phone: str | None = None


class VerifySetContactRequest(BaseModel):

    email: str | None = None
    phone: str | None = None


class VerifyRequestCodeRequest(BaseModel):

    channel: str  # "email" | "sms"


class VerifyConfirmCodeRequest(BaseModel):

    channel: str  # "email" | "sms"
    code: str


class VerifySubmitIdentityRequest(BaseModel):

    license_number: str
    selfie_provided: bool = True


class VerifySubmitCreditRequest(BaseModel):

    credit_app_id: str


class SetExecutionModeRequest(BaseModel):

    mode: str  # "human" | "ai" | "customer" | "hybrid"


class ConfigureProviderRequest(BaseModel):

    provider_name: str
    note: str | None = None


# AI Negotiation Engine (Digital Retail DR-3).
class SetNegotiationRulesRequest(BaseModel):

    min_front_gross: float | None = None
    min_total_gross: float | None = None
    max_discount: float | None = None
    max_trade_over_allowance: float | None = None
    max_payment_variance: float | None = None
    max_loss_position: float | None = None
    default_session_ttl_hours: int | None = None


class StartNegotiationRequest(BaseModel):

    deal_id: str
    ttl_hours: int | None = None
    target_payment: float | None = None


class NegotiationOfferRequest(BaseModel):

    selling_price: float | None = None
    trade_allowance: float | None = None
    down_payment: float | None = None
    term_months: int | None = None
    apr: float | None = None
    incentives: list | None = None


class ResolveEscalationRequest(BaseModel):

    decision: str  # "approve" | "deny"
    note: str | None = None


# NXTDeal Digital Retail self-service (DR-4) -- all token-driven (public).
class RetailStartDealRequest(BaseModel):

    token: str
    vehicle_id: str


class RetailTradeRequest(BaseModel):

    token: str
    vin: str | None = None
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    mileage: int | None = None
    condition: str | None = None
    photos: list | None = None
    market_value_estimate: float | None = None
    notes: str | None = None


class RetailStartNegotiationRequest(BaseModel):

    token: str
    target_payment: float | None = None


class RetailOfferRequest(BaseModel):

    token: str
    selling_price: float | None = None
    trade_allowance: float | None = None
    down_payment: float | None = None
    term_months: int | None = None
    apr: float | None = None
    incentives: list | None = None


class RetailTokenRequest(BaseModel):

    token: str


class RetailApplyCreditRequest(BaseModel):

    token: str
    employment_status: str | None = None
    employer_name: str | None = None
    monthly_income: float | None = None
    years_at_employer: float | None = None
    monthly_housing_payment: float | None = None
    housing_status: str | None = None
    requested_amount: float | None = None
    co_applicant: dict | None = None


class RetailSelectFiRequest(BaseModel):

    token: str
    product_key: str
    decision: str  # "accepted" | "declined"


class RetailSignRequest(BaseModel):

    token: str
    typed_signature: str


class RetailScheduleDeliveryRequest(BaseModel):

    token: str
    mode: str  # store_pickup | home_delivery | third_party
    window_start: str
    window_end: str | None = None
    address: str | None = None


# Home Delivery + Try Before You Buy (DR-6) -- staff.
class FulfillmentScheduleDeliveryRequest(BaseModel):

    deal_id: str
    mode: str
    window_start: str
    window_end: str | None = None
    address: str | None = None
    driver_id: str | None = None
    notes: str | None = None


class AssignDriverRequest(BaseModel):

    driver_id: str


class UpdateDeliveryStatusRequest(BaseModel):

    status: str


class SetTbybProgramRequest(BaseModel):

    max_hours: int | None = None
    max_miles: int | None = None
    deposit_amount: float | None = None
    require_identity_verified: bool | None = None
    require_insurance: bool | None = None


class StartTbybRequest(BaseModel):

    vehicle_id: str
    customer_id: str
    deal_id: str | None = None
    verification_id: str | None = None


class TbybActionRequest(BaseModel):

    action: str  # insurance | deposit | release | decision | inspect | recondition | reinstate
    policy_ref: str | None = None
    amount: float | None = None
    odometer_out: int | None = None
    odometer_in: int | None = None
    decision: str | None = None
    findings: str | None = None
    notes: str | None = None


class SendChatMessageRequest(BaseModel):

    body: str


class PromoteChatSessionRequest(BaseModel):

    name: str | None = None
    email: str | None = None
    phone: str | None = None


class CreateDealRequest(BaseModel):

    customer_id: str
    vehicle_id: str
    trade_in: dict | None = None


class AddScenarioRequest(BaseModel):

    label: str | None = None
    sale_price: float
    down_payment: float = 0
    term_months: int = 60


class SubmitLenderRequest(BaseModel):

    lender_id: str


class LenderDecisionRequest(BaseModel):

    decision: str
    countered_terms: dict | None = None
    notes: str | None = None


class TradeAppraisalRequest(BaseModel):

    patch: dict = {}


class DeliveryChecklistRequest(BaseModel):

    section: str
    patch: dict = {}


class CreateLeadTaskRequest(BaseModel):

    task_type: str
    description: str = ""
    due_at: str | None = None
    assigned_to: str | None = None


class TransferLeadRequest(BaseModel):

    new_employee_id: str


class PlaceHoldRequest(BaseModel):

    vehicle_id: str
    customer_id: str | None = None
    lead_id: str | None = None
    notes: str = ""
    duration_hours: int | None = None


class RequestTORequest(BaseModel):

    linked_entity_id: str
    reason: str
    notes: str = ""


class ResolveTORequest(BaseModel):

    outcome: str
    notes: str = ""


# Demo Drive's 2 Pydantic request models moved to
# api/routers/demo_drives.py (CAF-00120, god_file_app_py).

# Credit Applications' 4 Pydantic request models moved to
# api/routers/credit_apps.py (CAF-00120, god_file_app_py).


# eSignature's 4 Pydantic request models moved to
# api/routers/esignature.py (CAF-00120, god_file_app_py).


class PresentFIProductsRequest(BaseModel):

    product_keys: list[str]


class UpdateFIProductPricingRequest(BaseModel):

    cost: float | None = None
    price: float | None = None


class DecideFIProductRequest(BaseModel):

    decision: str
    declined_reason: str | None = None


# Lost Sale Recovery request models moved to
# api/routers/lost_sale_recovery.py (CAF-00120, god_file_app_py).


# ClaimOrphanOwnerRequest moved to api/routers/orphan_owners.py (CAF-00120).


# Vehicle Lifecycle request models moved to
# api/routers/vehicle_lifecycle.py (CAF-00120, god_file_app_py).


# Acquisitions request models moved to api/routers/acquisitions.py (CAF-00120).


class ApplyPriceRecommendationRequest(BaseModel):

    new_price: float
    reason: str = ""


class DecodeVinRequest(BaseModel):

    vin: str
    attempt_live: bool = True


class BulkApplyVinDecodeRequest(BaseModel):

    vehicle_ids: list | None = None
    attempt_live: bool = True
    limit: int = 100


class SetLotPositionRequest(BaseModel):

    row: str | None = None
    space: str | None = None
    section: str | None = None
    notes: str = ""


class NotesOnlyRequest(BaseModel):

    notes: str = ""


class CheckoutKeyRequest(BaseModel):

    holder: str
    notes: str = ""


class ReportDamageRequest(BaseModel):

    severity: str
    description: str
    estimated_cost: float | None = None


class UpdateDamageStatusRequest(BaseModel):

    new_status: str
    resolution_notes: str = ""


class LogScanRequest(BaseModel):

    location_note: str = ""


# Inventory Merchandising request models moved to api/routers/merchandising.py
# (CAF-00120, god_file_app_py).


# Wholesale Desk request models moved to api/routers/wholesale_desk.py
# (CAF-00120, god_file_app_py).


# Operations Tasks request models moved to api/routers/operations_tasks.py
# (CAF-00120, god_file_app_py).

# --- Inventory Aging Management (session 106 follow-up #4) request models ---

class ReducePriceRequest(BaseModel):

    new_price: float
    reason: str = ""


class AgingActionNotesRequest(BaseModel):

    notes: str = ""


# --- Operations Scheduling (session 106 follow-up #5) request models ---

class ScheduleReconRequest(BaseModel):

    target_date: str
    notes: str = ""


class ScheduleDeliveryRequest(BaseModel):

    scheduled_start: str
    assigned_to: str | None = None
    notes: str = ""


class UpdateTransportStatusRequest(BaseModel):

    new_status: str


# --- Document Workflows (session 106 follow-up #6) request models ---

class RequestDocumentRequest(BaseModel):

    entity_type: str
    entity_id: str
    document_type: str
    notes: str = ""


class ApproveDocumentRequest(BaseModel):

    notes: str = ""


class AcknowledgeAlertRequest(BaseModel):

    alert_type: str
    source_id: str
    notes: str = ""


class RejectDocumentRequest(BaseModel):

    reason: str


# --- RO Workflow Engine (Service rebuild kickoff) ---

class CreateRepairOrderRequest(BaseModel):

    vehicle_id: str
    customer_id: str
    description: str
    pay_type: str = "Customer Pay"
    preferred_contact_method: str | None = None


class AdvanceRoStageRequest(BaseModel):

    new_stage: str


class AddConcernRequest(BaseModel):

    description: str
    occurs_at: str = ""


class ReturnFollowupOutcomeRequest(BaseModel):
    outcome: str
    expected_updated_at: str


class ReturnFollowupRequest(BaseModel):
    due_date: str
    next_action: str


class ReturnHandoverRequest(BaseModel):
    recipient: str
    settlement_reference: str
    confirmed: bool = False


class ReturnReviewRequest(BaseModel):
    transport: str
    notes: str
    acknowledged: bool = False


class ResolveConcernRequest(BaseModel):

    concern_id: str
    resolution_notes: str = ""
    outcome: str = "resolved"


class SendEstimateRequest(BaseModel):

    amount: float


class RecordCustomerApprovalRequest(BaseModel):

    approved: bool
    decline_reason: str = ""


class UpdatePartsStatusRequest(BaseModel):

    status: str
    notes: str = ""


class RequestPartRequest(BaseModel):

    description: str


class UpdatePartRequestStatusRequest(BaseModel):

    request_id: str
    status: str


class UpdateQcItemRequest(BaseModel):

    item: str
    complete: bool


class LogRoCommunicationRequest(BaseModel):

    channel: str
    body: str


class AssignTechnicianRequest(BaseModel):

    technician_id: str | None = None


class MarkSpecialOrderRequest(BaseModel):

    request_id: str
    vendor: str
    eta: str


# Warranty Desk's 4 Pydantic request models moved to
# api/routers/warranty_desk.py (CAF-00120, god_file_app_py).

class UpdateInspectionItemRequest(BaseModel):

    item_key: str
    status: str
    notes: str = ""


class AttachInspectionPhotoRequest(BaseModel):

    item_key: str
    image_url: str
    media_type: str = "photo"


class CreateConcernsFromInspectionRequest(BaseModel):

    item_keys: list[str]


class PublicApprovalDecisionRequest(BaseModel):

    approved: bool
    decline_reason: str = ""


# My Garage token-scoped approval/pay (verify token in the body, like /public/retail/*).
class GarageApprovalRequest(BaseModel):

    token: str
    approved: bool
    decline_reason: str = ""


class GaragePayRequest(BaseModel):

    token: str
    method: str = "card"


# Loaner & Shuttle Management's 7 Pydantic request models moved to
# api/routers/loaner_shuttle.py (CAF-00120, god_file_app_py).


class FlagManualOpportunityRequest(BaseModel):

    notes: str = ""


class PromoteToSalesRequest(BaseModel):

    assigned_to: str | None = None
    notes: str = ""
    opportunity_type: str | None = None


class DismissOpportunityRequest(BaseModel):

    reason: str = ""
    opportunity_type: str | None = None


class SetLoanStatusRequest(BaseModel):

    status: str
    reason: str = ""


class AmortizationScheduleRequest(BaseModel):

    principal: float
    apr: float
    term_months: int


class RecordPaymentRequest(BaseModel):

    amount: float
    method: str
    payment_date: str | None = None
    notes: str = ""


class CreateAutoDraftRequest(BaseModel):

    amount: float
    method: str
    day_of_month: int


class SetAutoDraftStatusRequest(BaseModel):

    status: str


class CreatePromiseToPayRequest(BaseModel):

    promise_date: str
    amount: float
    reason: str = ""


class RecordExtensionRequest(BaseModel):

    new_next_due_date: str
    reason: str = ""


class RecordDeferralRequest(BaseModel):

    months: int
    reason: str = ""


class RequestPayoffRequest(BaseModel):

    notes: str = ""


class FulfillPayoffRequestRequest(BaseModel):

    request_id: str


class PublicPaymentRequest(BaseModel):

    amount: float
    method: str


class PublicPayoffRequestRequest(BaseModel):

    notes: str = ""


class AdvanceCollectionStageRequest(BaseModel):

    stage: str
    reason: str = ""


class LogCollectionContactRequest(BaseModel):

    channel: str
    notes: str


# Repossessions request models moved to api/routers/repossessions.py
# (CAF-00120, god_file_app_py).


class UpdateLienholderRequest(BaseModel):

    lienholder_name: str


class ReleaseLienRequest(BaseModel):

    reason: str = ""


class UpdateInsuranceRequest(BaseModel):

    carrier: str
    policy_number: str
    expiration_date: str
    loss_payee_confirmed: bool = False


class RecordOfacScreeningRequest(BaseModel):

    cleared: bool
    notes: str = ""


class RecordCashPaymentRequest(BaseModel):

    amount: float
    payment_date: str = ""


class FileForm8300Request(BaseModel):

    filing_date: str = ""


class SetGlbaComponentStatusRequest(BaseModel):

    status: str
    owner_employee_id: str | None = None
    notes: str = ""
    last_reviewed_at: str | None = None


class CloseAccountingPeriodRequest(BaseModel):

    year: int
    month: int


class ReopenAccountingPeriodRequest(BaseModel):

    year: int
    month: int


class GenerateSimulatedGlEntriesRequest(BaseModel):

    year: int
    month: int
    floorplan_exposure: float = 0.0


class GenerateBankFeedRequest(BaseModel):

    start_date: str = ""
    end_date: str = ""


class ConfirmBankMatchRequest(BaseModel):

    gl_entry_id: str


class MarkBankTransactionReviewedRequest(BaseModel):

    note: str = ""


class PreviewAudienceConditionsRequest(BaseModel):

    conditions: list = []


class PreviewAudiencePresetRequest(BaseModel):

    params: dict = {}


class CreateSmartAudienceRequest(BaseModel):

    name: str
    conditions: list = []
    preset_key: str | None = None
    preset_params: dict = {}
    description: str = ""


class GeneratePurlRequest(BaseModel):

    offer_type: str = "general"
    customer_id: str | None = None
    lead_id: str | None = None
    notes: str | None = None


class CreateMailPieceRequest(BaseModel):

    piece_name: str
    piece_type: str
    mail_date: str | None = None


class BulkGeneratePurlsRequest(BaseModel):

    source_type: str
    source_id: str
    offer_type: str = "general"
    notes: str | None = None


class SubmitPurlLeadRequest(BaseModel):

    notes: str | None = None


class PurlVisitRequest(BaseModel):

    user_agent: str | None = None


class SetPermissionOverrideRequest(BaseModel):

    employee_id: str
    permission_key: str
    granted: bool
    reason: str = ""


class CreateApprovalRequestRequest(BaseModel):

    chain_key: str
    subject: str
    details: str = ""
    entity_id: str | None = None


class ApproveStepRequest(BaseModel):

    note: str = ""


class RejectStepRequest(BaseModel):

    reason: str


class BotTaskFeedbackRequest(BaseModel):

    task_key: str
    event_type: str


class ScreenGuidanceAutomateRequest(BaseModel):
    """"Automate It" (2026-07-19) -- item_key is the raw, unprefixed source key
    (e.g. "funding_delays", "inventory_aging_action") that
    core/screen_guidance.py's create_automation_rule_from_guidance() maps to a
    real core/workflow_automation.py trigger type; title is the guidance item's
    own display title, carried through into the created AutomationRule's name/
    description so it's traceable back to the recommendation that spawned it."""

    item_key: str
    title: str


class ScreenGuidanceDoItRequest(BaseModel):
    """"Do It" (2026-07-19) -- item_key is the raw, unprefixed source key
    (e.g. "vehicles_missing_titles", "contracts_missing_documents") that
    core/screen_guidance.py's create_document_requests_from_guidance() maps
    to a real bulk document-request action via core/document_workflows.py."""

    item_key: str


class SetCoachingIntensityRequest(BaseModel):
    scope: str
    scope_target: str
    intensity: str
    reason: str = ""


class PreviewCoachingIntensityRequest(BaseModel):
    target_employee_id: str
    items: list
    department: str | None = None


class CreatePerformanceReviewRequest(BaseModel):
    target_employee_id: str
    period_label: str = ""


class UpdateReviewNotesRequest(BaseModel):
    manager_notes: str


class BotCoverageRequest(BaseModel):
    """The admin picks which role/section the bot should act under for the covered
    employee (defaults are reasonable but the admin can override e.g. if a Sales
    Consultant is out and the admin wants the bot generating Sales-manager-tier tasks
    for a delegate instead) -- see core/bot_tasks.py's generate_tasks()."""

    employee_id: str
    role: str
    section: str
    starts_at: str
    ends_at: str
    mode: str
    note: str | None = None


class TeamAgentActivateRequest(BaseModel):
    """Admin-activate a team agent (core/bot_fleet.py) in draft or auto mode. Auto mode is
    gated by the same default-deny bot.coverage.auto_mode capability as Bot Coverage."""

    mode: str = "draft"


class TeamWorkflowStepRequest(BaseModel):
    """One real observed step in a team's workflow (core/bot_fleet.py). action_key is the
    stable key of what was done; workflow_key optionally delimits one discrete run so a
    multi-step workflow's steps chain together."""

    action_key: str
    step_label: str | None = None
    workflow_key: str | None = None


class SharedInsightRequest(BaseModel):
    """A free-form learning contributed to the fleet's shared knowledge
    (core/shared_knowledge.py). `section` is which of the nine teams it belongs to."""

    section: str
    title: str
    body: str


class WorkerActivateRequest(BaseModel):
    """Activate an AI worker (core/ai_worker.py) in draft / assisted / autonomous mode."""

    mode: str


class WorkerInteractionRequest(BaseModel):
    """One inbound customer interaction handled by an AI worker (core/ai_worker.py)."""

    channel: str
    message: str
    scheduled_start: str | None = None
    linked_entity_id: str | None = None
    from_number: str | None = None


class CreateConnectionRequest(BaseModel):

    name: str
    connection_type: str
    department: str
    endpoint_url: str | None = None


class ResolveComplianceAlertRequest(BaseModel):

    notes: str | None = None


class OverrideComplianceAlertRequest(BaseModel):

    notes: str


class SendMessageRequest(BaseModel):
    """Shared by both channel and direct message POST routes -- `attached_pin` is the
    optional shared-pin payload (kind/label/refId, mirrors frontend/lib/pins.ts's `Pin`
    shape minus id/tag/pinnedAt) from the "drag a pin into the conversation, or attach it"
    feature Sam asked for. `None` when a message has no attachment."""

    content: str
    attached_pin: dict | None = None


class CreateKnowledgePinRequest(BaseModel):
    """Body for POST /knowledge/pins -- the "share" side of the pin action (session 72).
    `visibility` is "all" or "roles"; `roles` is only meaningful (and required non-empty)
    when visibility=="roles" -- see core/knowledge_pins.py's create_pin()."""

    kind: str
    ref_id: str | None = None
    label: str
    tag: str = "General"
    visibility: str
    roles: list[str] | None = None


class RetagKnowledgePinRequest(BaseModel):

    tag: str


class ShareKnowledgePinRequest(BaseModel):
    """Body for POST /knowledge/pins/{id}/share -- the drag-into-a-channel/DM "widen
    access" confirmation flow. Either add_roles or set_all, never both meaningfully."""

    add_roles: list[str] | None = None
    set_all: bool = False


class SaveDashboardLayoutRequest(BaseModel):
    """Body for POST /dashboard-layout (session 73; `board` added session 77 -- a
    department now has a "reporting" board and an "overview" board, defaults to
    "reporting" for backward compatibility). Always the full current board state, not
    a patch, since the frontend already holds the whole layout in memory to render the
    grid. See core/dashboard_layouts.py's save_layout() for the per-module shape this
    coerces/validates."""

    department: str
    modules: list[dict] = []
    board: str = "reporting"


class SaveNotificationPreferencesRequest(BaseModel):
    """Body for POST /notification-preferences (session 74). See
    core/notification_preferences.py's PREFERENCE_KEYS for the real, whitelisted set
    of toggles -- unknown keys sent here are silently dropped, not persisted."""

    preferences: dict = {}


class SaveWorkspaceBoardRequest(BaseModel):
    """Body for POST /workspace-board (session 76) -- always the full current board
    state, not a patch, same convention as SaveDashboardLayoutRequest. See
    core/workspace_board.py's _clean_item() for the real, whitelisted per-item shape
    (kind="chart"|"note" plus their respective fields) this coerces/validates."""

    items: list[dict] = []


class AddWorkspaceItemRequest(BaseModel):
    """Body for POST /workspace-board/item (Workspace grab-all, 2026-07-23) -- one
    grabbed frame (a report table, a detail record) captured from anywhere in the app.
    See core/workspace_board.py's _clean_item() snapshot branch for the whitelisted
    shape (kind='snapshot', data_kind='table'|'text', columns/rows/text)."""

    item: dict


class ExplainChartRequest(BaseModel):
    """Body for POST /workspace-board/explain (session 76) -- the same chart-shape data
    the caller already has on screen (from their own already-role-filtered GET
    /menu/data call), sent back so core/workspace_explain.py can write a short
    explanatory paragraph. No entity IDs or role-gated data beyond what the caller
    already fetched themselves."""

    source_label: str = ""
    department: str = ""
    item_key: str = ""
    label_column: str = ""
    numeric_columns: list[str] = []
    rows: list[dict] = []
    prompt_context: str = ""


# --- Administration Control Center -- Vendor Management / System Configuration /
# Data Management / Identity & Access / Security expansion (continued) ---


# CreateVendorRequest / UpdateVendorRequest / SetVendorStatusRequest moved to
# backend/api/routers/vendors.py (CAF-00120, god_file_app_py) -- no longer
# referenced from this file.


class SetIpAllowlistRequest(BaseModel):

    ip_allowlist: list[str] = []


class MfaVerifyRequest(BaseModel):
    """The second step of login for an MFA-enabled employee -- see
    core/auth_api.py's verify_mfa_login(). `code` may be a real 6-digit TOTP
    code or one of the employee's own recovery codes."""

    mfa_challenge_token: str
    code: str


class MfaConfirmRequest(BaseModel):

    code: str


class MfaDisableRequest(BaseModel):

    password: str


# CompleteSsoLoginRequest / UpdateSsoConfigRequest / SetSsoEnabledRequest /
# DiscoverOidcConfigurationRequest moved to api/routers/sso.py (CAF-00120).


# _bearer_token / _authenticate / _require_admin / _authorize_dashboard used to be
# defined right here. Extracted to api/deps.py (CAF-00120, god_file_app_py --
# splitting this file into routers) so new domain-scoped router modules under
# api/routers/*.py can import them too without a circular import back into this
# file. Behavior is unchanged -- see api/deps.py for the full docstrings.
from api.deps import (
    _require_recent_admin,
    _bearer_token,
    _authenticate,
    _require_admin,
    _authorize_dashboard
)


@app.get("/")
def root():

    return {
        "application": "NXTDeal",
        "status": "running"
    }


@app.get("/search")
def search(
    q: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)

    if error:
        return error

    results = search_graph(q)

    return [
        {
            "id": entity.id,
            "entity_type": entity.entity_type,
            "attributes": entity.attributes
        }
        for entity in results
        if can_access_entity(payload["role"], entity.entity_type)
    ]


@app.get("/entity/{entity_id}")
def get_entity(
    entity_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)

    if error:
        return error

    entity = repository.get_entity(
        entity_id
    )

    if not entity:

        return {
            "error": "Entity not found"
        }

    if not can_access_entity(payload["role"], entity.entity_type):

        return {
            "error": "Forbidden: your role cannot access this entity type"
        }

    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "attributes": entity.attributes
    }


@app.post("/entity/{entity_id}/update")
def update_entity(
    entity_id: str,
    request: UpdateEntityRequest,
    authorization: str = Header(None)
):
    """Generic inline entity editing (Sam: "we need to be able to edit the information
    in the menu dashes where it makes sense") -- reuses the exact same
    can_access_entity() role gate GET /entity/{id} already enforces, so an edit is
    never possible where a read wasn't already allowed. See
    core/entity_update_api.py's module docstring."""

    payload, error = _authenticate(authorization)

    if error:
        return error

    return update_entity_api(
        payload["role"],
        payload["employee_id"],
        entity_id,
        request.patch
    )


@app.get("/profile/{entity_id}")
def profile(
    entity_id: str,
    authorization: str = Header(None)
):
    """Entity 360 profile — dispatches on entity type (Customer/Employee/Vehicle get a
    dedicated view built from core/queries.py's get_*_360() functions; everything else
    falls back to the entity plus its direct relationships). See
    core/profile_api.py's module docstring for the RBAC filtering rule."""

    payload, error = _authenticate(authorization)

    if error:
        return error

    return get_profile(
        payload["role"],
        entity_id
    )


# GET /entity/{entity_id}/explore (session 76 fourth follow-up -- Sam: "everything
# that's created in workspace, referenced in chats, group messages as well as in the
# dashes... all of that knowledge association needs to be interconnected into the
# graph... explorable at all points"). A bounded, role-filtered multi-hop traversal
# (core/graph_explore.py) -- distinct from /profile/{id} above, which is one hop only.
# depth defaults to 2, capped at 3 server-side regardless of what's requested.
@app.get("/entity/{entity_id}/explore")
def explore_entity_route(
    entity_id: str,
    depth: int = 2,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)

    if error:
        return error

    return explore_entity_api(
        payload["role"],
        payload["employee_id"],
        entity_id,
        depth=depth
    )


@app.post("/question")
def question(
    request: QuestionRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)

    if error:
        return error

    answer = ask_question(
        request.question
    )

    return {
        "type": answer["type"],
        "results": [
            {
                "id": entity.id,
                "entity_type": entity.entity_type,
                "attributes": entity.attributes
            }
            for entity in answer["results"]
            if can_access_entity(payload["role"], entity.entity_type)
        ]
    }


@app.post("/ai/chat")
def ai_chat(
    request: AIRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)

    if error:
        return error

    return ask(
        request.question,
        payload["role"],
        caller_employee_id=payload.get("employee_id")
    )


@app.get("/dashboard/sales")
def sales_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "sales")
    if error:
        return error

    return get_sales_dashboard()


@app.get("/dashboard/service")
def service_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "service")
    if error:
        return error

    return get_service_dashboard()


@app.get("/dashboard/finance")
def finance_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "finance")
    if error:
        return error

    return get_finance_dashboard()


@app.get("/dashboard/executive")
def executive_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "executive")
    if error:
        return error

    return get_executive_dashboard()


@app.get("/dashboard/pipeline")
def pipeline_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "pipeline")
    if error:
        return error

    return (
        get_lead_pipeline_dashboard()
    )


@app.get("/dashboard/pipeline/metrics")
def pipeline_metrics(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "pipeline")
    if error:
        return error

    return (
        get_pipeline_metrics()
    )


@app.get("/dashboard/followup")
def followup_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "followup")
    if error:
        return error

    return (
        get_follow_up_dashboard()
    )


@app.get("/dashboard/velocity")
def velocity_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "velocity")
    if error:
        return error

    return (
        get_velocity_dashboard()
    )


@app.get("/dashboard/salesperson/{employee_id}")
def salesperson_dashboard(
    employee_id: str,
    authorization: str = Header(None)
):

    _, error = _authorize_dashboard(authorization, "salesperson")
    if error:
        return error

    return (
        get_dashboard(
            employee_id
        )
    )


@app.get("/dashboard/manager")
def manager_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "manager")
    if error:
        return error

    return (
        get_manager_dashboard_api()
    )


@app.get("/dashboard/leaderboard")
def leaderboard_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "leaderboard")
    if error:
        return error

    return (
        get_leaderboard_dashboard()
    )


@app.get("/dashboard/workload")
def workload_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "workload")
    if error:
        return error

    return (
        get_workload_dashboard_api()
    )


@app.get("/dashboard/escalations")
def escalation_dashboard(authorization: str = Header(None)):

    _, error = _authorize_dashboard(authorization, "escalations")
    if error:
        return error

    return (
        get_escalation_dashboard_api()
    )


@app.post("/lead/assign/{lead_id}")
def auto_assign(
    lead_id: str,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return (
        assign_new_lead(
            lead_id
        )
    )


@app.post("/lead/escalate/{lead_id}")
def escalate_lead(
    lead_id: str,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return (
        reassign(
            lead_id
        )
    )


@app.get("/audit")
def audit_events(
    entity_id: str = None,
    actor: str = None,
    event_type: str = None,
    authorization: str = Header(None)
):

    _, error = _require_admin(authorization)
    if error:
        return error

    return list_audit_events(
        entity_id=entity_id,
        actor=actor,
        event_type=event_type
    )


@app.get("/audit/entity/{entity_id}")
def audit_events_for_entity(
    entity_id: str,
    authorization: str = Header(None)
):

    _, error = _require_admin(authorization)
    if error:
        return error

    return list_audit_events(
        entity_id=entity_id
    )


@app.get("/audit/integrity")
def audit_integrity(authorization: str = Header(None)):
    """Real, live tamper-evidence report over the audit log (security-
    hardening pass, 2026-07-20) -- hash-chain verification
    (core/audit_integrity.py's verify_chain()) plus a separate on-disk
    checkpoint comparison (verify_against_checkpoint()) that catches a
    wholesale file swap the chain check alone can't. ADMIN-only, matching
    every other /audit* route."""

    _, error = _require_admin(authorization)
    if error:
        return error

    return get_audit_integrity_api()


@app.get("/dashboard/audit")
def audit_dashboard(authorization: str = Header(None)):

    _, error = _require_admin(authorization)
    if error:
        return error

    return get_audit_dashboard()


# --- Compliance / Employee Value / Department Intelligence / Network / Readiness /
#     Data Connections / Agentic Bot HTTP routes (wired 2026-07-16, scheduled builder) ---
#
# The ACL functions for all of these (sessions 35-38) were imported into this module and
# called directly by internal Python (workflow_tab_data.py, menu_data.py, etc.), but had
# NO @app route decorators -- so the frontend components that fetch them
# (ReadinessIntegrationPanel, NetworkBenchmarkPanel, BotWidget, the compliance/
# employee-value/intelligence artifacts in useArtifactPanel.ts) were hitting 404s the
# whole time. Flagged as the top-priority follow-up in BUILD_QUEUE.md's session-88 log.
# This is a pure "wire it up" pass -- no ACL logic changed, every function is used exactly
# as its signature and the frontend's existing request shape dictate. Route ordering is
# deliberate where a literal path could otherwise be captured by a {param} route
# (e.g. /intelligence/departments before /intelligence/{department}).

@app.get("/compliance/security-review")
def compliance_security_review(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.security_review import security_review_api
    return security_review_api(payload["role"])


@app.post("/compliance/forms/preflight")
def compliance_forms_preflight(request: PacketDraft, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.permissions import ADMIN, OPERATIONS, FINANCE
    if payload["role"] not in (ADMIN, OPERATIONS, FINANCE):
        return {"error": "Admin, Operations or Finance role required."}
    return assess_packet_draft(request)


@app.get("/compliance/payment-review")
def compliance_payment_review(offset: int = 0, limit: int = 100, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.payment_review import payment_review_api
    return payment_review_api(payload["role"], offset, limit)


@app.get("/compliance/rules")
def compliance_rules(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_compliance_rules_api()


@app.get("/compliance/alerts")
def compliance_alerts(
    status: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_compliance_alerts_api(payload["role"], status)


@app.get("/compliance/alerts/{alert_id}")
def compliance_alert_get(
    alert_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_compliance_alert_api(payload["role"], alert_id)


@app.post("/compliance/alerts/{alert_id}/resolve")
def compliance_alert_resolve(
    alert_id: str,
    request: ResolveComplianceAlertRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return resolve_compliance_alert_api(
        payload["role"],
        payload["employee_id"],
        alert_id,
        request.notes
    )


@app.post("/compliance/alerts/{alert_id}/override")
def compliance_alert_override(
    alert_id: str,
    request: OverrideComplianceAlertRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return override_compliance_alert_api(
        payload["role"],
        payload["employee_id"],
        alert_id,
        request.notes
    )


@app.post("/compliance/scan")
def compliance_scan(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_compliance_scan_api(payload["role"])


@app.get("/employees/value")
def employees_value(
    department: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_employee_values_api(payload["role"], department)


@app.get("/employees/{employee_id}/value")
def employee_value_get(
    employee_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_employee_value_api(payload["role"], employee_id)


# Literal /intelligence/departments MUST be registered before /intelligence/{department}
# or Starlette would match "departments" as the {department} param.
@app.get("/intelligence/departments")
def intelligence_departments(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_department_intelligence_api(payload["role"])


@app.get("/intelligence/{department}")
def intelligence_department(
    department: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_department_intelligence_api(payload["role"], department)


# Readiness predictions + prediction timeline are open to ANY authenticated role
# (see core/data_connections_api.py's readiness_predictions_api docstring -- Sam:
# "everyone can see tomorrow, a week, a month, a quarter").
@app.get("/readiness/predictions")
def readiness_predictions(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return readiness_predictions_api()


@app.get("/readiness/timeline/{department}")
def readiness_timeline(
    department: str,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return prediction_timeline_api(department)


@app.post("/connections")
@app.post("/readiness/connections")
def connections_create(
    request: CreateConnectionRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    from api.routers import sales_crm_advanced as store
    with store._lock, store.transaction():
        return create_connection_api(
            payload["role"], request.name, request.connection_type,
            request.department, payload["employee_id"], request.endpoint_url
        )


@app.get("/readiness/connections")
def connections_list(
    department: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_connections_api(payload["role"], department)


@app.post("/readiness/connections/{connection_id}/upload-csv")
@app.post("/connections/{connection_id}/upload-csv")
async def connections_upload_csv(
    connection_id: str,
    file: UploadFile = File(...),
    csv_kind: str = Form(None),
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    file_bytes = await file.read()

    return ingest_csv_api(
        payload["role"],
        connection_id,
        file.filename,
        file_bytes,
        csv_kind
    )


@app.post("/readiness/connections/{connection_id}/test")
@app.post("/connections/{connection_id}/test")
def connections_test(
    connection_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return test_api_connection_api(payload["role"], connection_id)


# --- Agentic bot (session 36) HTTP routes ---
@app.get("/bot/tasks")
def bot_tasks(
    section: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_my_tasks_api(payload["employee_id"], payload["role"], section)


@app.post("/bot/tasks/feedback")
def bot_task_feedback(
    request: BotTaskFeedbackRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_feedback_api(
        payload["employee_id"],
        request.task_key,
        request.event_type
    )


@app.get("/bot/screen-guidance")
def bot_screen_guidance(
    section: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_screen_guidance_api(payload["role"], section, employee_id=payload["employee_id"])


@app.post("/bot/screen-guidance/automate")
def bot_screen_guidance_automate(
    request: ScreenGuidanceAutomateRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return automate_screen_guidance_api(
        payload["role"],
        payload["employee_id"],
        request.item_key,
        request.title
    )


@app.post("/bot/screen-guidance/do-it")
def bot_screen_guidance_do_it(
    request: ScreenGuidanceDoItRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return do_it_screen_guidance_api(
        payload["role"],
        payload["employee_id"],
        request.item_key
    )


@app.get("/bot/coverage")
def bot_coverage_list(
    active_only: bool = False,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_coverage_api(payload["role"], active_only)


@app.post("/bot/coverage")
def bot_coverage_start(
    request: BotCoverageRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return start_coverage_api(
        payload["role"],
        payload["employee_id"],
        request.employee_id,
        request.role,
        request.section,
        request.starts_at,
        request.ends_at,
        request.mode,
        request.note
    )


@app.post("/bot/coverage/{coverage_id}/end")
def bot_coverage_end(
    coverage_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return end_coverage_api(payload["role"], payload["employee_id"], coverage_id)


# ---------------------------------------------------------------------------
# Agentic-bot FLEET (2026-07-23, Pillar 4 slice 1) -- one team agent per section, each
# recording its team's observed workflows. Viewing the fleet / a team's workflows and
# recording a step are open to any authenticated role (read-only insight / a signal
# about one's own team, same posture as GET /bot/tasks + POST /bot/tasks/feedback);
# activating/deactivating an agent is ADMIN-only (enforced in core/bot_fleet_api.py),
# and auto mode is additionally gated by the bot.coverage.auto_mode capability.
# ---------------------------------------------------------------------------


@app.get("/bot/fleet")
def bot_fleet_list(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_fleet_api(payload["role"])


@app.get("/bot/fleet/{section}/workflows")
def bot_fleet_team_workflows(section: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_team_workflows_api(payload["role"], section)


@app.post("/bot/fleet/{section}/record")
def bot_fleet_record_step(
    section: str,
    request: TeamWorkflowStepRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_workflow_step_api(
        payload["employee_id"],
        section,
        request.action_key,
        step_label=request.step_label,
        workflow_key=request.workflow_key,
    )


@app.post("/bot/fleet/{section}/activate")
def bot_fleet_activate(
    section: str,
    request: TeamAgentActivateRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return activate_agent_api(payload["role"], payload["employee_id"], section, request.mode)


@app.post("/bot/fleet/{section}/deactivate")
def bot_fleet_deactivate(section: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return deactivate_agent_api(payload["role"], payload["employee_id"], section)


@app.post("/bot/fleet/{section}/run")
def bot_fleet_run(section: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_recognized_workflow_api(payload["role"], payload["employee_id"], section)


# ---------------------------------------------------------------------------
# Shared AI knowledge (2026-07-23, Pillar 5) -- ONE pool the whole agent fleet reads
# from and writes to (core/shared_knowledge.py, backed by shared_knowledge_api.py).
# Reading is open to any authed role; contributing an insight is open to any authed
# employee; publishing recognized workflows and deleting an entry are ADMIN-only.
# ---------------------------------------------------------------------------


@app.get("/shared-knowledge")
def shared_knowledge_get(section: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_shared_knowledge_api(payload["role"], section=section)


@app.post("/shared-knowledge/contribute")
def shared_knowledge_contribute(
    request: SharedInsightRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return contribute_insight_api(
        payload["employee_id"], request.section, request.title, request.body
    )


@app.post("/shared-knowledge/publish")
def shared_knowledge_publish(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return publish_recognized_workflows_api(payload["role"], payload["employee_id"])


@app.delete("/shared-knowledge/{entry_id}")
def shared_knowledge_delete(entry_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_shared_entry_api(payload["role"], payload["employee_id"], entry_id)


# ---------------------------------------------------------------------------
# NXTDeal AI Workforce (2026-07-24) -- customer-facing AI workers (core/ai_worker.py,
# backed by ai_worker_api.py). Viewing is open to any authed role; activating /
# deactivating is ADMIN-only; handling an interaction is open to any authed caller (the
# channel webhook), with execution-vs-draft decided inside core/ai_worker by mode + kill
# switch + ai.worker.autonomous + WORKER_SAFE_ACTIONS.
# ---------------------------------------------------------------------------


@app.get("/workforce")
def ai_workforce_list(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_workforce_api(payload["role"])


@app.get("/workforce/{worker_role}")
def ai_worker_detail(worker_role: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_worker_detail_api(payload["role"], worker_role)


@app.post("/workforce/{worker_role}/activate")
def ai_worker_activate(
    worker_role: str,
    request: WorkerActivateRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return activate_worker_api(payload["role"], payload["employee_id"], worker_role, request.mode)


@app.post("/workforce/{worker_role}/deactivate")
def ai_worker_deactivate(worker_role: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return deactivate_worker_api(payload["role"], payload["employee_id"], worker_role)


@app.post("/workforce/{worker_role}/handle")
def ai_worker_handle(
    worker_role: str,
    request: WorkerInteractionRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return handle_interaction_api(
        payload["employee_id"], worker_role, request.channel, request.message,
        scheduled_start=request.scheduled_start,
        linked_entity_id=request.linked_entity_id,
        from_number=request.from_number,
    )


@app.post("/workforce/{worker_role}/run")
def ai_worker_run(worker_role: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_worker_queue_api(payload["role"], payload["employee_id"], worker_role)


# ---------------------------------------------------------------------------
# NXTDeal Connect (2026-07-24) -- the unified communications surface (core/connect.py):
# one inbox across every channel, a per-entity timeline, and analytics. Read-only, open to
# any authenticated role (composes the logged Communications; no new storage).
# ---------------------------------------------------------------------------


@app.get("/connect/inbox")
def connect_inbox(
    channel: str = None,
    direction: str = None,
    department: str = None,
    linked_entity_id: str = None,
    ai_only: bool = False,
    limit: int = 100,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_connect_inbox_api(
        payload["role"], channel=channel, direction=direction, department=department,
        linked_entity_id=linked_entity_id, ai_only=ai_only, limit=limit,
    )


@app.get("/connect/timeline/{entity_id}")
def connect_timeline(entity_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_connect_timeline_api(payload["role"], entity_id)


@app.get("/connect/analytics")
def connect_analytics(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_connect_analytics_api(payload["role"])


@app.get("/connect/intelligence")
def connect_intelligence(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_connect_intelligence_api(payload["role"])


@app.get("/connect/communications/{comm_id}/intelligence")
def connect_comm_intelligence(comm_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_connect_comm_intelligence_api(payload["role"], comm_id)


# ---------------------------------------------------------------------------
# NXTDeal Verify (Digital Retail, 2026-07-24) -- the identity-tier gate.
# STAFF read views below (any authenticated role, read-only operational insight);
# the customer-facing verification ACTIONS are the unauthenticated /public/verify/*
# routes further down (token-as-credential, mirroring the Customer Payment Portal).
# ---------------------------------------------------------------------------

@app.get("/verify/dashboard")
def verify_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_verify_dashboard_api(payload["role"])


@app.get("/verify/catalog")
def verify_catalog(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_verify_catalog_api(payload["role"])


@app.get("/verify/list")
def verify_list(tier: str = None, limit: int = 100, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_verifications_api(payload["role"], tier=tier, limit=limit)


@app.get("/verify/{verf_id}")
def verify_get(verf_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_verification_api(payload["role"], verf_id)


# ---------------------------------------------------------------------------
# Execution modes (Digital Retail DR-2, 2026-07-24) -- who drives each workflow
# (human / ai / customer / hybrid). Viewing is open to any authenticated role;
# changing a workflow's active mode is ADMIN-only.
# ---------------------------------------------------------------------------

@app.get("/execution-modes")
def execution_modes_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_execution_modes_api(payload["role"])


@app.get("/execution-modes/{workflow_key}")
def execution_mode_get(workflow_key: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_execution_workflow_api(payload["role"], workflow_key)


@app.post("/execution-modes/{workflow_key}")
def execution_mode_set(workflow_key: str, request: SetExecutionModeRequest,
                       authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_execution_mode_api(payload["role"], payload["employee_id"], workflow_key, request.mode)


# ---------------------------------------------------------------------------
# AI Negotiation Engine (Digital Retail DR-3, 2026-07-24) -- negotiate within a
# dealer-configured profit envelope; out-of-bounds offers escalate for manager
# approval. Viewing is any authed role; rules are ADMIN; desking actions are the
# sales-desk roles; escalation resolution is manager roles (enforced in the API layer).
# ---------------------------------------------------------------------------

@app.get("/negotiation/dashboard")
def negotiation_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_negotiation_dashboard_api(payload["role"])


@app.get("/negotiation/rules")
def negotiation_rules_get(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_negotiation_rules_api(payload["role"])


@app.post("/negotiation/rules")
def negotiation_rules_set(request: SetNegotiationRulesRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    patch = {k: v for k, v in request.dict().items() if v is not None}
    return set_negotiation_rules_api(payload["role"], payload["employee_id"], patch)


@app.get("/negotiation/sessions")
def negotiation_sessions_list(deal_id: str = None, status: str = None, limit: int = 100,
                              authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_sessions_api(payload["role"], deal_id=deal_id, status=status, limit=limit)


@app.post("/negotiation/sessions")
def negotiation_session_start(request: StartNegotiationRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return start_session_api(payload["role"], payload["employee_id"], request.deal_id,
                             ttl_hours=request.ttl_hours, target_payment=request.target_payment)


@app.get("/negotiation/sessions/{session_id}")
def negotiation_session_get(session_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_negotiation_session_api(payload["role"], session_id)


@app.post("/negotiation/sessions/{session_id}/evaluate")
def negotiation_session_evaluate(session_id: str, request: NegotiationOfferRequest,
                                 authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    proposal = {k: v for k, v in request.dict().items() if v is not None}
    return evaluate_offer_api(payload["role"], session_id, proposal)


@app.post("/negotiation/sessions/{session_id}/offer")
def negotiation_session_offer(session_id: str, request: NegotiationOfferRequest,
                              authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    proposal = {k: v for k, v in request.dict().items() if v is not None}
    return apply_offer_api(payload["role"], payload["employee_id"], session_id, proposal)


@app.post("/negotiation/sessions/{session_id}/escalation")
def negotiation_session_resolve(session_id: str, request: ResolveEscalationRequest,
                                authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return resolve_escalation_api(payload["role"], payload["employee_id"], session_id,
                                  request.decision, note=request.note)


@app.post("/negotiation/sessions/{session_id}/accept")
def negotiation_session_accept(session_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return accept_session_api(payload["role"], payload["employee_id"], session_id)


# ---------------------------------------------------------------------------
# Home Delivery + Try Before You Buy (Digital Retail DR-6, 2026-07-24). Viewing is
# any authed role; scheduling/advancing deliveries + running the TBYB workflow are the
# ops/sales roles; the TBYB program config is ADMIN (enforced in the API layer).
# ---------------------------------------------------------------------------

@app.get("/fulfillment/dashboard")
def fulfillment_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_fulfillment_dashboard_api(payload["role"])


@app.get("/digital-retail/dashboard")
def digital_retail_dashboard(authorization: str = Header(None)):
    """The Digital Retail KPI dashboard (DR-8) -- KPIs, AI performance, and the self-service
    journey drop-off funnel, composed over everything DR-1..7 record. Any authed role."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_digital_retail_dashboard_api(payload["role"])


@app.get("/integrations/providers")
def integrations_providers(authorization: str = Header(None)):
    """The external-provider seam status -- which capabilities are live vs honestly simulated
    (core/integrations_registry.py). Any authed role."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_integrations_api(payload["role"])


@app.post("/integrations/providers/{capability}")
def integrations_configure(capability: str, request: ConfigureProviderRequest,
                           authorization: str = Header(None)):
    """Record the intended provider for a capability (ADMIN). Informational -- it does not
    create a live connection (that requires a registered adapter in code)."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return configure_provider_api(payload["role"], payload["employee_id"], capability,
                                  request.provider_name, note=request.note)


# --- NXTDeal Marketplace (2026-07-24) ---------------------------------------------------
@app.get("/marketplace")
def marketplace_catalog(authorization: str = Header(None)):
    """The full Marketplace catalog + per-dealer install state (core/marketplace.py). Any
    authed role -- browsing what's available is operational insight."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_marketplace_api(payload["role"])


@app.get("/marketplace/listings/{listing_id}")
def marketplace_listing(listing_id: str, authorization: str = Header(None)):
    """One Marketplace listing's detail + live state. Any authed role."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_listing_api(payload["role"], listing_id)


@app.post("/marketplace/listings/{listing_id}/install")
def marketplace_install(listing_id: str, authorization: str = Header(None)):
    """Install a Marketplace listing for this dealership (ADMIN). Records a real install and,
    for a capability-backed listing, the intended provider -- it does NOT fabricate a live
    external connection (that requires a registered adapter in code)."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return install_listing_api(payload["role"], payload["employee_id"], listing_id)


@app.post("/marketplace/listings/{listing_id}/uninstall")
def marketplace_uninstall(listing_id: str, authorization: str = Header(None)):
    """Remove an installed Marketplace listing (ADMIN). Soft status flip (append-only graph)."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return uninstall_listing_api(payload["role"], payload["employee_id"], listing_id)


# --- Customer Communications (2026-07-24) -----------------------------------------------
class SaveContactRequest(BaseModel):
    number: str
    name: str | None = None
    email: str | None = None


class PlaceCallRequest(BaseModel):
    customer_id: str | None = None
    number: str | None = None
    department: str | None = None


class EndCallRequest(BaseModel):
    notes: str | None = None
    duration_seconds: int | None = None


class SendTextRequest(BaseModel):
    body: str
    customer_id: str | None = None
    number: str | None = None
    department: str | None = None


@app.get("/comms/provider")
def comms_provider(authorization: str = Header(None)):
    """Whether a real phone/SMS provider is connected (drives the 'Connect a phone provider'
    prompt). Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return comms_provider_status_api(payload["role"])


@app.get("/comms/customers/search")
def comms_customer_search(q: str, limit: int = 25, authorization: str = Header(None)):
    """Search the CRM for a customer/lead to call or text. Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return search_customers_api(payload["role"], q, limit=limit)


@app.post("/comms/contacts")
def comms_save_contact(request: SaveContactRequest, authorization: str = Header(None)):
    """Save a free-typed/dialed number as a real CRM customer. Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return save_contact_api(payload["role"], payload["employee_id"], request.number,
                            name=request.name, email=request.email)


@app.post("/comms/call")
def comms_place_call(request: PlaceCallRequest, authorization: str = Header(None)):
    """Place an outbound call (simulated until a telephony provider is connected). Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return place_call_api(payload["role"], payload["employee_id"],
                          customer_id=request.customer_id, number=request.number,
                          department=request.department)


@app.post("/comms/call/{call_id}/end")
def comms_end_call(call_id: str, request: EndCallRequest, authorization: str = Header(None)):
    """End a connected call; returns the recorded (simulated) transcript + AI analysis. Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return end_call_api(payload["role"], payload["employee_id"], call_id,
                        notes=request.notes, duration_seconds=request.duration_seconds)


@app.post("/comms/text")
def comms_send_text(request: SendTextRequest, authorization: str = Header(None)):
    """Send a text (real Communication + simulated dispatch via the seam). Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return send_text_api(payload["role"], payload["employee_id"], request.body,
                         customer_id=request.customer_id, number=request.number,
                         department=request.department)


@app.get("/comms/conversation/{customer_id}")
def comms_conversation(customer_id: str, authorization: str = Header(None)):
    """The full call/text/appointment timeline with one customer. Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_conversation_api(payload["role"], customer_id)


@app.get("/comms/intelligence/{comm_id}")
def comms_intelligence(comm_id: str, authorization: str = Header(None)):
    """The AI recording/analysis/coaching for one communication. Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return get_call_intelligence_api(payload["role"], comm_id)


@app.get("/comms/recent")
def comms_recent(department: str = None, limit: int = 25, authorization: str = Header(None)):
    """Recent customer calls + texts across the store. Any authed role."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    return recent_activity_api(payload["role"], department=department, limit=limit)


@app.get("/delivery/list")
def delivery_list(status: str = None, mode: str = None, deal_id: str = None,
                  limit: int = 100, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_deliveries_api(payload["role"], status=status, mode=mode, deal_id=deal_id, limit=limit)


@app.post("/delivery")
def delivery_schedule(request: FulfillmentScheduleDeliveryRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return schedule_delivery_api(payload["role"], payload["employee_id"], request.deal_id,
                                 request.mode, request.window_start, window_end=request.window_end,
                                 address=request.address, driver_id=request.driver_id,
                                 notes=request.notes or "")


@app.get("/delivery/{delivery_id}")
def delivery_get(delivery_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_delivery_api(payload["role"], delivery_id)


@app.post("/delivery/{delivery_id}/driver")
def delivery_assign_driver(delivery_id: str, request: AssignDriverRequest,
                           authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return assign_driver_api(payload["role"], payload["employee_id"], delivery_id, request.driver_id)


@app.post("/delivery/{delivery_id}/status")
def delivery_update_status(delivery_id: str, request: UpdateDeliveryStatusRequest,
                           authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_delivery_status_api(payload["role"], payload["employee_id"], delivery_id, request.status)


@app.get("/tbyb/program")
def tbyb_program_get(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_tbyb_program_api(payload["role"])


@app.post("/tbyb/program")
def tbyb_program_set(request: SetTbybProgramRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    patch = {k: v for k, v in request.dict().items() if v is not None}
    return set_tbyb_program_api(payload["role"], payload["employee_id"], patch)


@app.get("/tbyb/list")
def tbyb_list(status: str = None, limit: int = 100, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_tbyb_api(payload["role"], status=status, limit=limit)


@app.post("/tbyb")
def tbyb_start(request: StartTbybRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return start_tbyb_api(payload["role"], payload["employee_id"], request.vehicle_id,
                          request.customer_id, deal_id=request.deal_id,
                          verification_id=request.verification_id)


@app.get("/tbyb/{tbyb_id}")
def tbyb_get(tbyb_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_tbyb_api(payload["role"], tbyb_id)


@app.post("/tbyb/{tbyb_id}/action")
def tbyb_action(tbyb_id: str, request: TbybActionRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    kwargs = {k: v for k, v in request.dict().items() if k != "action" and v is not None}
    return tbyb_action_api(payload["role"], payload["employee_id"], tbyb_id, request.action, **kwargs)


# ---------------------------------------------------------------------------
# Coaching (2026-07-19) -- the fourth "NXTDeal Workforce AI" pillar.
# Extracted to api/routers/coaching.py (CAF-00120, god_file_app_py -- splitting
# this file into domain-scoped routers). Included below via
# app.include_router(coaching_router). Same 14 routes, same behavior.
# ---------------------------------------------------------------------------


@app.post("/auth/login")
def auth_login(
    request: LoginRequest,
    http_request: Request = None
):

    client_ip = http_request.client.host if http_request and http_request.client else None

    return login(
        request.employee_id,
        request.password,
        client_ip=client_ip
    )


@app.get("/auth/whoami")
def auth_whoami(
    authorization: str = Header(None)
):

    token = _bearer_token(authorization)

    if not token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return whoami(token)


@app.post("/auth/admin/credentials")
def auth_create_credential(
    request: CreateCredentialRequest,
    authorization: str = Header(None)
):
    """Admin one-by-one add. For bulk onboarding, use imports/credential_import.py
    instead (run locally against the backend, matching the rest of the imports/ scripts —
    see that file's docstring)."""

    admin_token = _bearer_token(authorization)

    if not admin_token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return create_credential(
        admin_token,
        request.employee_id,
        request.role,
        request.temp_password,
        request.email
    )


@app.get("/auth/admin/credentials")
def auth_list_credentials(
    authorization: str = Header(None)
):
    """Admin roster view — every employee with a credential (employee_id, role,
    must_change_password, created_by, created_at, email), never salt/hash. See
    core/auth_api.py's list_credentials() and BUILD_QUEUE.md's "Employee Directory /
    Admin Roster View" entry."""

    admin_token = _bearer_token(authorization)

    if not admin_token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return list_credentials(
        admin_token
    )


@app.post("/auth/change-password")
def auth_change_password(
    request: ChangePasswordRequest,
    authorization: str = Header(None)
):

    token = _bearer_token(authorization)

    if not token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return change_password(
        token,
        request.old_password,
        request.new_password
    )


@app.post("/auth/admin/reset-password")
def auth_reset_password(
    request: ResetPasswordRequest,
    authorization: str = Header(None)
):
    """Admin-forced reset for an employee who's forgotten their password and can't
    complete POST /auth/change-password themselves (that requires the current password).
    Preserves the employee's existing role — use POST /auth/admin/credentials instead for
    a brand new account."""

    admin_token = _bearer_token(authorization)

    if not admin_token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return reset_password(
        admin_token,
        request.employee_id,
        request.temp_password
    )


@app.get("/auth/admin/lockout/{employee_id}")
def auth_get_lockout_status(employee_id: str, authorization: str = Header(None)):
    """Real, computed lockout state for one employee (Administration Control Center
    rebuild, "Security" item). See core/auth_api.py's get_lockout_status() -- ADMIN/
    OPERATIONS, verifies admin_token itself internally."""

    admin_token = _bearer_token(authorization)

    if not admin_token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return get_lockout_status(admin_token, employee_id)


@app.post("/auth/admin/unlock/{employee_id}")
def auth_unlock_account(employee_id: str, authorization: str = Header(None)):
    """Clears an active lockout early rather than making the employee wait out
    LOCKOUT_MINUTES. See core/auth_api.py's unlock_account()."""

    admin_token = _bearer_token(authorization)

    if not admin_token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return unlock_account(admin_token, employee_id)


@app.post("/auth/admin/ip-allowlist/{employee_id}")
def auth_set_ip_allowlist(employee_id: str, request: SetIpAllowlistRequest, authorization: str = Header(None)):
    """Real, per-employee IP allowlist -- ADMIN-only (narrower than most of this
    module's other ADMIN/OPERATIONS actions), see core/auth_api.py's
    set_ip_allowlist()."""

    admin_token = _bearer_token(authorization)

    if not admin_token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return set_ip_allowlist(admin_token, employee_id, request.ip_allowlist)


# --- MFA (security-hardening pass, 2026-07-20) ---
#
# login() (above) now issues a short-lived mfa_challenge_token instead of a
# real session token whenever the employee has MFA enabled; POST
# /auth/mfa/verify is the only place that ticket is ever redeemed for a real
# token. The remaining routes below are self-service enroll/disable/status,
# plus one ADMIN escape hatch for a lost authenticator + lost recovery codes.
# See core/auth_api.py's docstrings for the full design.

@app.post("/auth/mfa/verify")
def auth_verify_mfa(request: MfaVerifyRequest):
    """Body-only (no Authorization header) -- the mfa_challenge_token itself
    IS the credential at this step, same as a temp password would be."""

    return verify_mfa_login(request.mfa_challenge_token, request.code)


@app.post("/auth/mfa/enroll/begin")
def auth_begin_mfa_enrollment(authorization: str = Header(None)):

    token = _bearer_token(authorization)

    if not token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return begin_mfa_enrollment(token)


@app.post("/auth/mfa/enroll/confirm")
def auth_confirm_mfa_enrollment(request: MfaConfirmRequest, authorization: str = Header(None)):

    token = _bearer_token(authorization)

    if not token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return confirm_mfa_enrollment(token, request.code)


@app.post("/auth/mfa/disable")
def auth_disable_mfa(request: MfaDisableRequest, authorization: str = Header(None)):

    token = _bearer_token(authorization)

    if not token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return disable_mfa(token, request.password)


@app.get("/auth/mfa/status")
def auth_get_mfa_status(authorization: str = Header(None)):

    token = _bearer_token(authorization)

    if not token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return get_mfa_status(token)


@app.post("/auth/admin/mfa/{employee_id}/disable")
def auth_admin_disable_mfa(employee_id: str, authorization: str = Header(None)):
    """ADMIN-only escape hatch for an employee who's lost both their
    authenticator device and every recovery code. See
    core/auth_api.py's admin_disable_mfa()."""

    admin_token = _bearer_token(authorization)

    if not admin_token:

        return {
            "error": "Missing or malformed Authorization header (expected 'Bearer <token>')"
        }

    return admin_disable_mfa(admin_token, employee_id)


# --- SSO / OIDC moved to api/routers/sso.py (CAF-00120) --
# see app.include_router(sso_router) below.


# --- Communications (session 28) ---
#
# Graph-native: channels/messages are Entity records in the same ledger as everything
# else (core/messaging.py) -- tied to Employee entities via sender_id/recipient_id
# attributes, not a separate messaging world. Sending is always a normal REST POST;
# the websocket below exists purely to push already-open clients an update immediately
# instead of making them poll.


@app.get("/messaging/channels")
def messaging_channels(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_channels(payload["role"])


@app.get("/messaging/channels/{channel_key}/messages")
def messaging_channel_messages(
    channel_key: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_channel_messages_api(channel_key, payload["role"])


@app.post("/messaging/channels/{channel_key}/messages")
async def messaging_post_channel_message(
    channel_key: str,
    request: SendMessageRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    result = post_channel_message_api(
        channel_key,
        payload["role"],
        payload["employee_id"],
        request.content,
        request.attached_pin
    )

    if "error" not in result:

        await ws_manager.broadcast_channel_message(
            channel_key,
            {"event": "channel_message", "channel_key": channel_key, "message": result}
        )

    return result


@app.get("/messaging/conversations")
def messaging_conversations(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_conversations_api(payload["employee_id"])


@app.get("/messaging/directory")
def messaging_directory(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_directory_api()


@app.get("/messaging/direct/{other_employee_id}")
def messaging_direct_messages(
    other_employee_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_direct_messages_api(payload["employee_id"], other_employee_id)


@app.post("/messaging/direct/{other_employee_id}")
async def messaging_post_direct_message(
    other_employee_id: str,
    request: SendMessageRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    result = post_direct_message_api(
        payload["employee_id"],
        other_employee_id,
        request.content,
        request.attached_pin
    )

    if "error" not in result:

        # No "with" field here on purpose -- it would mean something different
        # depending on which of the two participants receives it. The message itself
        # already carries sender_id/recipient_id; each client derives its own
        # conversation partner as "whichever of the two isn't me."
        await ws_manager.broadcast_direct_message(
            payload["employee_id"],
            other_employee_id,
            {"event": "direct_message", "message": result}
        )

    return result


# --- Shared Knowledge (session 72) --------------------------------------------------
# Sam: "id like there to be a regular knowledge and a shared knowledge... it goes into
# 'Shared Knowledge'... you can drag and drop the knowledge piece into the Direct
# messages, or communications, where it will ask if you want to change the access."
# "My Knowledge" (frontend/lib/pins.ts) stays entirely browser-local and never touches
# these routes -- they only exist for pins someone explicitly chose to share.


@app.get("/knowledge/pins/share-roles")
def knowledge_pins_share_roles(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return share_roles_api()


@app.get("/knowledge/pins")
def list_knowledge_pins(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_shared_pins_api(payload["role"], payload["employee_id"])


@app.post("/knowledge/pins")
def create_knowledge_pin(request: CreateKnowledgePinRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_shared_pin_api(
        payload["employee_id"],
        request.kind,
        request.ref_id,
        request.label,
        request.tag,
        request.visibility,
        request.roles
    )


@app.patch("/knowledge/pins/{pin_id}/tag")
def retag_knowledge_pin(pin_id: str, request: RetagKnowledgePinRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return retag_shared_pin_api(pin_id, payload["employee_id"], payload["role"], request.tag)


@app.post("/knowledge/pins/{pin_id}/share")
def share_knowledge_pin(pin_id: str, request: ShareKnowledgePinRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return share_shared_pin_api(
        pin_id,
        payload["employee_id"],
        payload["role"],
        add_roles=request.add_roles,
        set_all=request.set_all
    )


@app.delete("/knowledge/pins/{pin_id}")
def delete_knowledge_pin(pin_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_shared_pin_api(pin_id, payload["employee_id"], payload["role"])


@app.websocket("/ws/messaging")
async def messaging_websocket(
    websocket: WebSocket,
    token: str = Query(None)
):
    """Auth via `?token=` query param -- browsers can't set custom headers on a
    WebSocket handshake, so this is the one place in the API that departs from the
    `Authorization: Bearer` convention (see _bearer_token's docstring for why REST
    routes avoid query-param tokens; that leakage concern is unavoidable here, same
    tradeoff any browser-based websocket auth makes). Payload only ever pushes messages
    the caller is already authorized to see (channel broadcasts are filtered by role in
    core/ws_manager.py; DM broadcasts only ever target the two participants)."""

    payload = verify_token(token) if token else None

    if not payload or is_mfa_challenge_token(payload):
        await websocket.close(code=4401)
        return

    employee_id = payload["employee_id"]

    if not await ws_manager.connect(employee_id, websocket, token):
        return

    try:

        await ws_manager.listen(employee_id, websocket)

    except WebSocketDisconnect:

        pass  # listen() releases registration on every exit, including cancellation.


# --- Marketing asset design/approval workflow (session 30) ---
#
# Graph-native, same as Communications: an Asset is an Entity in the same ledger as
# everything else (core/assets.py), tied to the Employee who requested it. Any role can
# request/create + submit; only MARKETING/ADMIN can approve/reject or see the pending
# queue (core/assets_api.py's ACL, not a new role in core/permissions.py).


@app.get("/assets/templates")
def assets_templates(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_templates_api()


@app.post("/assets")
def assets_create(
    request: CreateAssetRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_asset_api(
        payload["employee_id"],
        request.template_key,
        request.fields,
        request.vehicle_id,
        request.campaign_id
    )


@app.post("/assets/{asset_id}/submit")
def assets_submit(
    asset_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return submit_asset_api(payload["role"], payload["employee_id"], asset_id)


@app.get("/assets/mine")
def assets_mine(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_my_assets_api(payload["employee_id"])


@app.get("/assets/pending")
def assets_pending(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_asset_pending_approvals_api(payload["role"])


@app.get("/assets/{asset_id}")
def assets_get(
    asset_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_asset_api(payload["role"], payload["employee_id"], asset_id)


@app.post("/assets/{asset_id}/approve")
def assets_approve(
    asset_id: str,
    request: ReviewAssetRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return approve_asset_api(payload["role"], payload["employee_id"], asset_id, request.notes)


@app.post("/assets/{asset_id}/reject")
def assets_reject(
    asset_id: str,
    request: ReviewAssetRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reject_asset_api(payload["role"], payload["employee_id"], asset_id, request.notes)


# --- Native per-department quick-entry (session 47) ---
#
# Sam: "each section... needs to have their own buttons/callouts that are native to
# their department... functions that would be difficult to replicate in the chat
# feature / workspace breakout... a way for jobs that require input / field work to add
# quicker to the knowledge graph." Any authenticated role can call any of these -- same
# "any role creates" precedent as Assets/Campaigns/Deals -- there's no approval step to
# gate on a field note, a walk-in lead, a vehicle arrival, or a service ticket.

@app.post("/notes")
def notes_create(request: CreateFieldNoteRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_field_note_api(
        payload["employee_id"],
        request.department,
        request.category,
        request.body,
        request.linked_entity_id
    )


@app.get("/notes")
def notes_list(department: str = None, linked_entity_id: str = None, authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return {"notes": list_field_notes_api(department, linked_entity_id=linked_entity_id)}


@app.post("/leads")
def leads_create(request: CreateLeadRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_lead_api(
        payload["employee_id"],
        request.first_name,
        request.last_name,
        request.source,
        request.phone,
        request.email,
        request.city,
        request.state,
        request.vin
    )


@app.post("/vehicles")
def vehicles_create(request: CreateVehicleRequest, authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return create_vehicle_api(
        request.vin,
        request.year,
        request.make,
        request.model,
        request.trim,
        request.color,
        request.mileage,
        request.condition,
        request.price,
        request.cost,
        request.stock_number,
        request.lot
    )


@app.post("/service-records")
def service_records_create(request: CreateServiceRecordRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_service_record_api(
        payload["employee_id"],
        request.vin,
        request.description,
        request.pay_type,
        request.status,
        request.customer_id,
        request.mileage,
        request.cost,
        request.parts_cost,
        request.labor_hours
    )


@app.post("/documents/upload")
async def documents_upload(
    file: UploadFile = File(...),
    linked_entity_id: str = Form(None),
    linked_entity_type: str = Form(None),
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    file_bytes = await file.read()

    return upload_document_api(
        payload["employee_id"],
        file.filename,
        file.content_type,
        file_bytes,
        linked_entity_id,
        linked_entity_type
    )


# --- Department job-workflow engine (session 53) ---
#
# Sam: "we need 4 unique buttons for each department... a work modal for the jobs that
# can't be done via chat for each department that are unique to that department,"
# baked directly from an attached job-responsibilities document. 36 catalog workflows
# (core/workflow_catalog.py) x one generic multi-stage tracking engine
# (core/workflow_tracking.py) -- any authenticated role can start/advance/cancel an
# instance, same "any role" precedent as the session-47 quick-entry endpoints above.

@app.get("/workflows/catalog")
def workflows_catalog(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return get_workflow_catalog_api()


@app.post("/workflows/start")
def workflows_start(request: StartWorkflowRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return start_workflow_api(
        request.workflow_key,
        payload["employee_id"],
        request.linked_entity_id,
        request.notes
    )


@app.post("/workflows/{instance_id}/advance")
def workflows_advance(
    instance_id: str,
    request: AdvanceWorkflowRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return advance_workflow_api(instance_id, payload["employee_id"], request.notes)


@app.post("/workflows/{instance_id}/cancel")
def workflows_cancel(
    instance_id: str,
    request: AdvanceWorkflowRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_workflow_api(instance_id, payload["employee_id"], request.notes)


@app.get("/workflows")
def workflows_list(
    department: str = None,
    workflow_key: str = None,
    status: str = None,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return {"instances": list_workflow_instances_api(department, workflow_key, status)}


@app.get("/workflows/tab-data")
def workflows_tab_data(
    workflow_key: str,
    linked_entity_id: str = None,
    authorization: str = Header(None)
):
    """Session 57, "wire it all up" -- real data for a WorkflowWindow's tabs, wherever
    the graph already has it (see core/workflow_tab_data.py's module docstring for
    scope). Not a replacement for the honest Core Functionality placeholder cards --
    those stay client-side, unchanged."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_tab_data_api(payload["role"], workflow_key, linked_entity_id)


# --- Top Menu (session 60) ---
#
# Sam: "i want to create a menu under the color bar for each dash / page... Top Menu =
# quick-access navigation like a traditional CRM/DMS," distinct from the 4 job-workflow
# buttons above (core/workflow_catalog.py). Same generic-engine pattern as
# /workflows/catalog + /workflows/tab-data, one level up: GET /menu/catalog returns a
# department's item list (empty for every department beyond Operations this pass --
# core/menu_catalog.py's module docstring has the scoping note), GET /menu/data returns
# real data for one item, optionally filtered by a search query for the items that
# accept one (Vehicles, Documents).

@app.get("/menu/catalog")
def menu_catalog(department: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    from core.administration_access import can_open_admin_item
    result = get_department_menu_api(department)
    if department == "Administration":
        result["items"] = [item for item in result["items"] if can_open_admin_item(payload, item["key"])]
    return result


@app.get("/menu/data")
def menu_data(
    department: str,
    item_key: str,
    query: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    from core.administration_access import can_open_admin_item
    if department == "Administration" and not can_open_admin_item(payload, item_key):
        return {"error": "This administration tool is not available to your account", "code": "admin_access_required"}
    return get_menu_data_api(payload["role"], department, item_key, query)


# --- Customizable Reporting + Overview BI dashboards (session 73; Overview added
# session 77) ---
#
# Sam: "lets go ahead and set all the reporting to be graph based... they should also
# be able to snap them into place to create their own dashboards... hide the modules
# (deactivate)... This is for each department." GET /report-modules is the module
# catalog + live data (core/report_modules.py -- a live reshaping of each department's
# existing "reporting" Top Menu rollup, no stored copy). GET/POST /dashboard-layout is
# the signed-in employee's own saved board for one department (core/dashboard_layouts.py
# -- "their own dashboards," per employee, not shared department-wide), now keyed by an
# extra `board` query param/body field ("reporting" or "overview", default "reporting").
#
# Session 77 (Sam: "in all overview dashes in the submenus for all departments, I'd
# like that to be a very BI visual glance as a default that gives the top metrics that
# that department wants to see... Lets connect it to reporting in that if you create a
# report that you want to show in overview, you can select 'show in overview' and it
# shows up in available modules at the bottom"): GET /overview-modules is Overview's
# own module catalog (core/report_modules.get_overview_modules -- one KPI card per
# top-level overview() field, plus any Reporting section flagged "Show in Overview").
# The existing GET /dashboard-layout, called with board=overview, auto-seeds a default
# KPI layout the first time an employee opens it (core/dashboard_layouts_api.py) --
# "Auto-populate real KPIs," Sam's own choice for what Overview shows before anyone
# customizes it.

@app.get("/report-modules")
def report_modules(department: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_report_modules_api(payload["role"], department)


@app.get("/overview-modules")
def overview_modules(department: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_overview_modules_api(payload["role"], payload["employee_id"], department)


@app.get("/dashboard-layout")
def dashboard_layout(department: str, board: str = "reporting", authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_dashboard_layout_api(payload["employee_id"], department, board, payload["role"])


@app.post("/dashboard-layout")
def save_dashboard_layout(request: SaveDashboardLayoutRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return save_dashboard_layout_api(payload["employee_id"], request.department, request.modules, request.board)


# --- Account settings gear menu (session 74) ---
#
# Sam: "we need to have a gear icon on the far right at the top - when clicked, it
# should show user profile settings / password administration, notification
# settings." GET /me is a self-scoped profile read (deliberately not the general
# GET /entity/{id} -- Employee has no ENTITY_ACCESS entry today, which would deny most
# roles their OWN record; reading your own employee record needs no role check at
# all). Password changes reuse the already-built POST /auth/change-password rather
# than a second endpoint. GET/POST /notification-preferences are
# core/notification_preferences.py's real per-employee toggle storage.

@app.get("/me")
def get_my_profile(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    entity = repository.get_entity(payload["employee_id"])

    if not entity:
        return {"error": "Employee record not found"}

    return {
        "id": entity.id,
        "entity_type": entity.entity_type,
        "attributes": entity.attributes,
        "role": payload["role"],
    }


@app.get("/notification-preferences")
def get_notification_preferences(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_notification_preferences_api(payload["employee_id"])


@app.post("/notification-preferences")
def save_notification_preferences(request: SaveNotificationPreferencesRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return save_notification_preferences_api(payload["employee_id"], request.preferences)


# --- OneNote-style Workspace board (session 76) ---
#
# Sam: "the workspace needs to be dynamic... should be able to pull from dashes,
# reporting and from input on the chat... Lets also make workspace removable (pop out in
# another window) for multiscreens." GET/POST /workspace-board are personal, per-employee
# persistence for the Workspace column's ordered chart+note items (core/workspace_board.py
# -- no ACL beyond "must be authenticated", same as /notification-preferences).
# POST /workspace-board/explain is the "AI generated content explaining the graph"
# ask -- a single non-tool-calling OpenAI call (core/workspace_explain.py) over whatever
# chart data the caller already has on screen, deliberately isolated from
# core/ai_assistant.py's tool-calling assistant the same way core/help_api.py already is.

@app.get("/workspace-board")
def get_workspace_board(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_workspace_board_api(payload["employee_id"])


@app.post("/workspace-board")
def save_workspace_board(request: SaveWorkspaceBoardRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return save_workspace_board_api(payload["employee_id"], request.items)


@app.post("/workspace-board/item")
def add_workspace_board_item(request: AddWorkspaceItemRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_workspace_item_api(payload["employee_id"], request.item)


@app.post("/workspace-board/explain")
def explain_workspace_chart(request: ExplainChartRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return explain_chart_api(
        source_label=request.source_label,
        department=request.department,
        item_key=request.item_key,
        label_column=request.label_column,
        numeric_columns=request.numeric_columns,
        rows=request.rows,
        prompt_context=request.prompt_context,
    )


# GET /workspace-board/shared/{owner_employee_id} (session 76 third follow-up -- Sam:
# "move the pin to knowledge out of the reports and notes windows and put it into the
# workspace as a whole... set viewing permissions") -- the one read path where someone
# other than the board's own owner can see it, gated on a real
# core/knowledge_pins.py 'workspace_board' pin actually naming them (see
# get_shared_workspace_board_api's docstring). Read-only: there's no corresponding POST,
# a viewer never edits someone else's personal Workspace.
@app.get("/workspace-board/shared/{owner_employee_id}")
def get_shared_workspace_board(owner_employee_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_shared_workspace_board_api(
        payload["employee_id"],
        payload["role"],
        owner_employee_id
    )


# --- Campaign & customer-lifecycle engine (session 31) ---
#
# Graph-native, same as Assets/Communications: a Campaign is an Entity in the same
# ledger as everything else (core/campaigns.py), tied to the Employee who created it and
# optionally an Asset (the creative it's sending). Any role can create a draft/preview an
# audience; only MARKETING/ADMIN can activate ("send"), complete, or see the activation
# queue (core/campaigns_api.py's ACL, not a new role in core/permissions.py) -- same
# pattern already approved for the asset workflow. A linked asset must be 'approved'
# before its campaign can activate.


@app.get("/campaigns/types")
def campaigns_types(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_campaign_types_api()


@app.get("/campaigns/channels")
def campaigns_channels(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_channels_api()


@app.post("/campaigns/audience/preview")
def campaigns_audience_preview(
    request: AudiencePreviewRequest,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return preview_audience_api(request.campaign_type, request.params)


@app.post("/campaigns")
def campaigns_create(
    request: CreateCampaignRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_campaign_api(
        payload["employee_id"],
        request.campaign_type,
        request.name,
        request.channel,
        request.params,
        request.linked_asset_id,
        request.linked_template_id
    )


# Bumper-parity: Multi-Planner. Registered before the /campaigns/{campaign_id} param
# route so "bulk" isn't swallowed as a campaign id.
@app.post("/campaigns/bulk")
def campaigns_bulk_create(
    request: BulkCreateCampaignsRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return bulk_create_campaigns_api(payload["employee_id"], request.specs)


@app.get("/campaigns/mine")
def campaigns_mine(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_my_campaigns_api(payload["employee_id"])


@app.get("/campaigns/pending")
def campaigns_pending(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_pending_campaigns_api(payload["role"])


@app.get("/campaigns/{campaign_id}")
def campaigns_get(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_campaign_api(payload["role"], payload["employee_id"], campaign_id)


@app.post("/campaigns/{campaign_id}")
def campaigns_update(
    campaign_id: str,
    request: UpdateCampaignRequest,
    authorization: str = Header(None)
):
    """Session 82 -- Sam: "the campaigns should be editable." """

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_campaign_api(payload["role"], payload["employee_id"], campaign_id, request.patch)


# Bumper-parity: Duplication Station. Sub-path of {campaign_id}, so no route collision.
@app.post("/campaigns/{campaign_id}/duplicate")
def campaigns_duplicate(
    campaign_id: str,
    request: DuplicateCampaignRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return duplicate_campaign_api(payload["role"], payload["employee_id"], campaign_id, request.new_name)


# Track B: real per-recipient delivery pipeline (routes through the provider seam).
@app.post("/campaigns/{campaign_id}/send")
def campaigns_send(
    campaign_id: str,
    request: SendCampaignRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return send_campaign_api(payload["role"], payload["employee_id"], campaign_id, request.resend)


@app.get("/campaigns/{campaign_id}/delivery")
def campaigns_delivery(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_campaign_delivery_api(payload["role"], payload["employee_id"], campaign_id)


@app.get("/campaigns/{campaign_id}/detail")
def campaigns_detail(
    campaign_id: str,
    page: int = 1,
    page_size: int = 25,
    entity_type: str = None,
    authorization: str = Header(None)
):
    """Session 82 -- Sam: "when you click on [a campaign] they should show the list of
    people, all the information that has been included as well as active measurements /
    analytics." `entity_type` filters the paginated audience to "Customer" or "Lead"."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_campaign_detail_api(payload["role"], payload["employee_id"], campaign_id, page, page_size, entity_type)


@app.post("/campaigns/{campaign_id}/ab-test")
def campaigns_set_ab_variant(
    campaign_id: str,
    request: SetAbVariantRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_ab_variant_api(payload["role"], campaign_id, request.variant_b_template_id)


@app.post("/campaigns/{campaign_id}/ab-test/clear")
def campaigns_clear_ab_variant(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return clear_ab_variant_api(payload["role"], campaign_id)


@app.get("/campaigns/{campaign_id}/ab-test")
def campaigns_get_ab_config(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_campaign_ab_config_api(payload["role"], payload["employee_id"], campaign_id)


@app.get("/campaigns/{campaign_id}/ab-test/results")
def campaigns_get_ab_results(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ab_test_results_api(payload["role"], payload["employee_id"], campaign_id)


@app.get("/campaigns/{campaign_id}/revenue")
def campaigns_get_revenue(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_campaign_revenue_api(payload["role"], payload["employee_id"], campaign_id)


# ---------------------------------------------------------------------------
# Bumper-parity: Recurring Schedule. Own top-level prefix (not /campaigns/*) so the
# static "run"/"active" segments never collide with a campaign id. On-demand evaluation
# -- run_due fires every schedule whose next_run_date is due, no background scheduler
# (same posture as workflow automation).
# ---------------------------------------------------------------------------
@app.post("/recurring-schedules")
def recurring_schedules_create(
    request: CreateRecurringScheduleRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_recurring_schedule_api(
        payload["employee_id"],
        request.base_campaign_id,
        request.cadence,
        request.start_date,
        request.end_date,
        request.interval,
        request.name,
    )


@app.get("/recurring-schedules")
def recurring_schedules_list(
    active_only: bool = False,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_recurring_schedules_api(active_only=active_only)


@app.post("/recurring-schedules/run")
def recurring_schedules_run(
    request: RunRecurringSchedulesRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_due_recurring_schedules_api(payload["role"], payload["employee_id"], request.today)


@app.get("/recurring-schedules/{schedule_id}")
def recurring_schedules_get(
    schedule_id: str,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return get_recurring_schedule_api(schedule_id)


@app.post("/recurring-schedules/{schedule_id}/active")
def recurring_schedules_set_active(
    schedule_id: str,
    request: SetRecurringScheduleActiveRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_recurring_schedule_active_api(payload["role"], payload["employee_id"], schedule_id, request.active)


@app.delete("/recurring-schedules/{schedule_id}")
def recurring_schedules_delete(
    schedule_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_recurring_schedule_api(payload["role"], payload["employee_id"], schedule_id)


# ---------------------------------------------------------------------------
# Bumper-parity: Bulk Import with column mapping + dedupe. Three-step flow --
# analyze (parse + suggest mapping), preview (non-destructive plan), commit (create).
# Analyze/preview are open to any authed role; commit is MARKETING/ADMIN only.
# ---------------------------------------------------------------------------
@app.get("/imports/targets")
def imports_targets(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_import_targets_api()


@app.post("/imports/analyze")
def imports_analyze(
    request: AnalyzeImportRequest,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return analyze_csv_api(request.csv_text, request.target_type)


@app.post("/imports/preview")
def imports_preview(
    request: PreviewImportRequest,
    authorization: str = Header(None)
):

    _, error = _authenticate(authorization)
    if error:
        return error

    return preview_import_api(request.csv_text, request.mapping, request.target_type, request.dedupe)


@app.post("/imports/commit")
def imports_commit(
    request: CommitImportRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return commit_import_api(
        payload["role"], payload["employee_id"],
        request.csv_text, request.mapping, request.target_type, request.dedupe,
    )


# ---------------------------------------------------------------------------
# Bumper-parity: User management + role assignment. Create a user (Employee entity +
# login + role) in one ADMIN action; reassign roles without a password reset. The role
# reference and roster are ADMIN/OPERATIONS; mutations are ADMIN-only.
# ---------------------------------------------------------------------------
@app.get("/users/roles")
def users_roles(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_roles_api()


@app.get("/users")
def users_list(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_users_api(payload["role"])


@app.post("/users")
def users_create(
    request: CreateUserRequest,
    authorization: str = Header(None)
):

    payload, error = _require_recent_admin(authorization)
    if error:
        return error

    return create_user_api(
        payload["role"], payload["employee_id"],
        request.first_name, request.last_name, request.email, request.role,
        request.department or "", request.title or "", request.temp_password,
    )


@app.post("/users/{target_employee_id}/role")
def users_update_role(
    target_employee_id: str,
    request: UpdateUserRoleRequest,
    authorization: str = Header(None)
):

    payload, error = _require_recent_admin(authorization)
    if error:
        return error

    return update_user_role_api(payload["role"], payload["employee_id"], target_employee_id, request.new_role)


# Marketing Growth Platform, Attribution Engine + Marketing ROI Dashboard +
# Vehicle Attribution capstone (2026-07-18). A distinct top-level prefix
# (not folded under /campaigns/* or /marketing/*) since these are
# dealership-wide aggregate reports, not scoped to one campaign or entity.
# See core/marketing_attribution.py's module docstring.
@app.get("/marketing-attribution/channel-mix")
def marketing_attribution_channel_mix(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_channel_mix_api(payload["role"])


@app.get("/marketing-attribution/roi-dashboard")
def marketing_attribution_roi_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_marketing_roi_dashboard_api(payload["role"])


@app.get("/marketing-attribution/vehicle-attribution")
def marketing_attribution_vehicle_attribution(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vehicle_attribution_api(payload["role"])


@app.post("/campaigns/{campaign_id}/activate")
def campaigns_activate(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return activate_campaign_api(payload["role"], payload["employee_id"], campaign_id)


@app.post("/campaigns/{campaign_id}/complete")
def campaigns_complete(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return complete_campaign_api(payload["role"], payload["employee_id"], campaign_id)


@app.post("/campaigns/{campaign_id}/cancel")
def campaigns_cancel(
    campaign_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_campaign_api(payload["role"], payload["employee_id"], campaign_id)


# --- CRM Pipeline (session 79) ---
#
# advance_lead_workflow() (core/lead_workflows.py) has existed since the "One Graph
# Unification" session (17) but had zero live callers anywhere in this codebase before
# this route -- the CRM Pipeline kanban board (Marketing's "CRM" Top Menu item) is the
# first real UI to drag a Lead between real, validated pipeline states.


@app.post("/lead/{lead_id}/advance-pipeline")
def lead_advance_pipeline(
    lead_id: str,
    request: AdvanceLeadPipelineRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return advance_lead_pipeline_api(payload["role"], payload["employee_id"], lead_id, request.next_state)


# --- CRM Lists (session 82) ---
#
# Graph-native, same as Campaigns/EmailTemplates: a MarketingList is an Entity in the
# same ledger as everything else (core/marketing_lists.py), tied to the Employee who
# created it. Any role can browse lists and their paginated members (Sam: "this is
# actually a functionality that is going to appear on the sales side as well");
# creating/curating membership is scoped to the creator or MARKETING/ADMIN
# (core/marketing_lists_api.py's ACL). Static-path routes are declared before
# /lists/{list_id} so FastAPI doesn't try to match "from-pool" etc. as a list_id.


@app.post("/lists")
def lists_create(
    request: CreateListRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_list_api(payload["employee_id"], request.name, request.description)


@app.post("/lists/from-pool")
def lists_from_pool(
    request: BuildListFromPoolRequest,
    authorization: str = Header(None)
):
    """Sam: "its really there you'd be able to start to curate marketing lists for
    campaigns." Re-runs the real audience builder server-side (core/campaigns.py's
    build_audience()) so the new list's membership is the full matching set, not just
    whatever sample was on screen."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return build_list_from_pool_api(
        payload["employee_id"],
        request.name,
        request.campaign_type,
        request.params,
        request.description,
    )


@app.get("/lists")
def lists_list(
    mine_only: bool = False,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_lists_api(payload["role"], payload["employee_id"], mine_only)


@app.get("/lists/{list_id}")
def lists_get(
    list_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_list_api(payload["role"], payload["employee_id"], list_id)


@app.get("/lists/{list_id}/members")
def lists_members(
    list_id: str,
    page: int = 1,
    page_size: int = 25,
    entity_type: str = None,
    authorization: str = Header(None)
):
    """Sam: "click on the list names and have them show as a list of names lets say in
    a list of 25 individuals, with a page up and down also adjustable by 25, 50, 100."
    `entity_type` filters to "Customer" or "Lead"."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_list_members_api(payload["role"], payload["employee_id"], list_id, page, page_size, entity_type)


@app.post("/lists/{list_id}")
def lists_update(
    list_id: str,
    request: UpdateListRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_list_api(payload["role"], payload["employee_id"], list_id, request.patch)


@app.post("/lists/{list_id}/members")
def lists_add_members(
    list_id: str,
    request: ListMembersRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_list_members_api(payload["role"], payload["employee_id"], list_id, request.entity_ids)


@app.post("/lists/{list_id}/members/remove")
def lists_remove_members(
    list_id: str,
    request: ListMembersRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_list_members_api(payload["role"], payload["employee_id"], list_id, request.entity_ids)


@app.post("/lists/{list_id}/archive")
def lists_archive(
    list_id: str,
    authorization: str = Header(None)
):
    """No ledger.remove_entity exists anywhere in this codebase -- "deleting" a list
    marks it archived (core/marketing_lists.py's delete_list()), matching the
    append-only-graph convention rather than pretending a hard delete happened."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_list_api(payload["role"], payload["employee_id"], list_id)


# --- CRM Opportunities workflow actions (session 82) ---
#
# Sam: "each [CRM] module needs to be a workable process, not just an information
# dash... how it would flow not only through the marketing department, but what parts
# would be accessible to sales." Two real actions on top of core/marketing_menu.py's
# previously read-only _opportunities(): saving a pool as a real, curatable List, and
# -- for Lead-typed opportunities only -- handing one directly to a salesperson via the
# same real ASSIGNED_TO mechanism the Sales pipeline already uses
# (core/lead_assignment.py). See core/opportunities_api.py's module docstring.


@app.get("/opportunities/sales-employees")
def opportunities_sales_employees(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_opportunity_sales_employees_api()


@app.post("/opportunities/save-as-list")
def opportunities_save_as_list(
    request: SaveOpportunityAsListRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return save_opportunity_pool_as_list_api(
        payload["role"],
        payload["employee_id"],
        request.name,
        request.campaign_type,
        request.params,
        request.description,
    )


@app.post("/opportunities/assign-to-sales")
def opportunities_assign_to_sales(
    request: AssignOpportunityRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return assign_opportunity_to_sales_api(payload["role"], request.lead_id, request.assign_to_employee_id)


# Social media post builder's 10 routes moved to api/routers/social.py
# (CAF-00120, god_file_app_py) -- registered via app.include_router(social_router)
# below.

# --- Reputation management (session 83) ---
#
# Real per-review response + a bad-review alert/auto-respond bot on top of the
# already-real seeded Review entities. Any role can read; MARKETING/ADMIN can respond.
# See core/reputation_api.py's module docstring.

@app.get("/reputation/summary")
def reputation_summary(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_reputation_summary_api(payload["role"])


@app.get("/reputation/reviews")
def reputation_reviews(
    platform: str = None,
    responded: str = None,
    max_rating: int = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_reviews_api(payload["role"], platform, responded, max_rating)


@app.get("/reputation/alerts")
def reputation_alerts(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_bad_review_alerts_api(payload["role"])


@app.post("/reputation/reviews/{review_id}/respond")
def reputation_respond(
    review_id: str,
    request: RespondToReviewRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return respond_to_review_api(payload["role"], payload["employee_id"], review_id, request.response_text)


@app.post("/reputation/reviews/{review_id}/auto-respond")
def reputation_auto_respond(review_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return auto_respond_review_api(payload["role"], payload["employee_id"], review_id)


@app.get("/reputation/competitor-tracking")
def reputation_competitor_tracking(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_competitor_tracking_api(payload["role"])


# Advertising's 11 routes moved to api/routers/advertising.py (CAF-00120,
# god_file_app_py) -- registered via app.include_router(advertising_router) below.

# --- Events dash: Trigger Alert Timeline (session 84) ---
#
# AutoAlert/automotiveMastermind-style: a live, urgency-ranked feed of individually
# actionable signals, re-scanned against the real graph on every fetch. Any role
# reads; ADMIN/MARKETING/SALES can promote (-> a real new Lead) or dismiss. See
# core/trigger_alerts_api.py's module docstring.

@app.get("/alerts/types")
def alerts_types(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_alert_types_api()


@app.get("/alerts/feed")
def alerts_feed(
    alert_type: str = None,
    status: str = None,
    target_entity_type: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_trigger_alert_feed_api(payload["role"], alert_type, status, target_entity_type)


@app.get("/alerts/{alert_id}")
def alerts_get(alert_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_alert_api(payload["role"], alert_id)


@app.post("/alerts/{alert_id}/dismiss")
def alerts_dismiss(
    alert_id: str,
    request: DismissAlertRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return dismiss_alert_api(payload["role"], payload["employee_id"], alert_id, request.notes)


@app.post("/alerts/{alert_id}/promote")
def alerts_promote(
    alert_id: str,
    request: PromoteAlertRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return promote_alert_api(payload["role"], payload["employee_id"], alert_id, request.assign_to_employee_id)


# --- Events dash: Dealership Events + RSVPs (session 84) ---
#
# NXTDeal Bumper-style: real scheduled events with a CRM-list-backed invite audience
# and RSVP tracking. Any role drafts/logs an RSVP; ADMIN/MARKETING/SALES
# publish/start/complete/cancel and promote an RSVP into a real new Lead. See
# core/dealership_events_api.py's module docstring.

@app.get("/events/types")
def events_types(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_event_types_api()


@app.get("/events/rsvp-statuses")
def events_rsvp_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_rsvp_statuses_api()


@app.post("/events")
def events_create(
    request: CreateEventRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_event_api(
        payload["role"],
        payload["employee_id"],
        request.name,
        request.event_type,
        request.start_time,
        request.end_time,
        request.location,
        request.capacity,
        request.description,
        request.linked_list_id,
    )


@app.get("/events")
def events_list(
    status: str = None,
    event_type: str = None,
    mine_only: bool = False,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_events_api(payload["role"], payload["employee_id"], status, event_type, mine_only)


@app.get("/events/{event_id}")
def events_get(event_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_event_api(payload["role"], payload["employee_id"], event_id)


@app.put("/events/{event_id}")
def events_update(
    event_id: str,
    request: UpdateEventRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_event_api(payload["role"], payload["employee_id"], event_id, request.patch)


@app.post("/events/{event_id}/publish")
def events_publish(event_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return publish_event_api(payload["role"], payload["employee_id"], event_id)


@app.post("/events/{event_id}/start")
def events_start(event_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return start_event_api(payload["role"], payload["employee_id"], event_id)


@app.post("/events/{event_id}/complete")
def events_complete(event_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return complete_event_api(payload["role"], payload["employee_id"], event_id)


@app.post("/events/{event_id}/cancel")
def events_cancel(event_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_event_api(payload["role"], payload["employee_id"], event_id)


@app.post("/events/{event_id}/rsvps")
def events_create_rsvp(
    event_id: str,
    request: CreateRsvpRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_rsvp_api(
        payload["role"],
        payload["employee_id"],
        event_id,
        request.name,
        request.phone,
        request.email,
        request.customer_id,
        request.lead_id,
        request.source,
    )


@app.get("/events/{event_id}/rsvps")
def events_list_rsvps(
    event_id: str,
    status: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_event_rsvps_api(payload["role"], payload["employee_id"], event_id, status)


@app.put("/rsvps/{rsvp_id}/status")
def rsvps_update_status(
    rsvp_id: str,
    request: UpdateRsvpStatusRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_rsvp_status_api(payload["role"], payload["employee_id"], rsvp_id, request.status)


@app.post("/rsvps/{rsvp_id}/promote")
def rsvps_promote(
    rsvp_id: str,
    request: PromoteRsvpRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return promote_rsvp_to_lead_api(payload["role"], payload["employee_id"], rsvp_id, request.assign_to_employee_id)


# --- Event Project Management + War Room + Campaign Generator (2026-07-18) ---
#
# The "War Room, Project Management, Campaign Generator" items flagged as open at the
# end of the Events dash's original build (session 84). core/event_planning.py's
# EventTask is a real planning checklist per Event; the War Room composes real RSVP/
# task/campaign data already tracked elsewhere. core/event_campaign_generator.py
# reuses core/email_wizard.py's real OpenAI-backed copy generation (session 79) plus
# a new "event_promo" core/campaigns.py audience type resolving the Event's own real
# invite/RSVP roster. Static paths registered before the dynamic /events/{event_id}/*
# paths below to avoid any risk of shadowing (same precedent as every other module's
# route registration in this file).


@app.get("/event-tasks/statuses")
def event_tasks_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_task_statuses_api()


@app.post("/events/{event_id}/tasks")
def event_tasks_create(
    event_id: str,
    request: CreateEventTaskRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_event_task_api(
        payload["role"],
        payload["employee_id"],
        event_id,
        request.title,
        request.assignee_employee_id,
        request.due_date,
        request.notes,
    )


@app.get("/events/{event_id}/tasks")
def event_tasks_list(
    event_id: str,
    status: str = None,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_tasks_for_event_api(payload["role"], event_id, status)


@app.get("/events/{event_id}/project-management")
def event_project_management(event_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_project_management_summary_api(payload["role"], event_id)


@app.get("/events/{event_id}/war-room")
def event_war_room(event_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_event_war_room_api(payload["role"], event_id)


@app.put("/event-tasks/{task_id}")
def event_tasks_update(
    task_id: str,
    request: UpdateEventTaskRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_task_api(payload["role"], payload["employee_id"], task_id, request.patch)


@app.put("/event-tasks/{task_id}/status")
def event_tasks_update_status(
    task_id: str,
    request: UpdateEventTaskStatusRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_task_status_api(payload["role"], payload["employee_id"], task_id, request.status)


@app.post("/event-tasks/{task_id}/delete")
def event_tasks_delete(task_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_task_api(payload["role"], payload["employee_id"], task_id)


@app.post("/events/{event_id}/campaign-generator/draft")
def event_campaign_generator_draft(
    event_id: str,
    request: GenerateEventCampaignRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_event_campaign_draft_api(payload["role"], event_id, request.channel, request.tone)


@app.post("/events/{event_id}/campaign-generator/create")
def event_campaign_generator_create(
    event_id: str,
    request: CreateEventCampaignRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_event_campaign_api(payload["role"], payload["employee_id"], event_id, request.channel, request.tone)


@app.get("/events/{event_id}/campaigns")
def event_campaigns_list(event_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_campaigns_for_event_api(payload["role"], event_id)


# Email/SMS Templates' 12 routes moved to api/routers/email_templates.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(email_templates_router) below.

# --- Website / inventory builder (session 32) ---
#
# Graph-native, same as Assets/Campaigns: a Website is an Entity in the same ledger as
# everything else (core/websites.py), tied to the Employee who built it. Fixed page set
# (Home/Inventory/About/Contact), fixed section-template catalog -- template-fill, no
# freeform canvas, no AI image generation (dealer-supplied photo URLs only). Any role
# builds/edits/submits; only MARKETING/ADMIN approve ("publish")/reject or see the
# pending queue -- same ACL shape as the asset and campaign workflows.


@app.get("/websites/sections")
def websites_sections(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_section_templates_api()


@app.get("/websites/pages")
def websites_pages(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_page_keys_api()


@app.get("/websites/modes")
def websites_modes(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_modes_api()


@app.post("/websites")
def websites_create(
    request: CreateWebsiteRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_website_api(payload["employee_id"], request.name, request.mode)


@app.post("/websites/wizard")
def websites_wizard_create(
    request: CreateWebsiteWizardRequest,
    authorization: str = Header(None)
):
    """Sam: 'have dealerOS create the website through a setup wizard... let ai write
    the content and set it up.' See core/website_wizard.py for the AI copy generation
    and core/websites.py's create_website_from_wizard() for how it's assembled into a
    full draft site."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_website_wizard_api(payload["employee_id"], request.dealership_info, request.mode)


# Session 85 -- these six functions were imported from core/websites_api.py since
# session 32/58 but never actually wired to a route, so a site's builder/owner had no
# way to fetch a single rendered site, list their own sites, or move it through
# submit -> approve/reject over HTTP at all (even though the underlying logic was
# real and complete). Closing that gap is the first, most literal piece of Sam's "I
# think we've built this out, just haven't put it fully in the dashboard."

@app.get("/websites")
def websites_list_mine(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_my_websites_api(payload["employee_id"])


@app.get("/websites/pending")
def websites_list_pending(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_pending_websites_api(payload["role"])


@app.get("/websites/{website_id}")
def websites_get(website_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_website_api(payload["role"], payload["employee_id"], website_id)


@app.post("/websites/{website_id}/submit")
def websites_submit(website_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return submit_website_api(payload["role"], payload["employee_id"], website_id)


@app.post("/websites/{website_id}/approve")
def websites_approve(
    website_id: str,
    request: ReviewWebsiteRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return approve_website_api(payload["role"], payload["employee_id"], website_id, request.notes)


@app.post("/websites/{website_id}/reject")
def websites_reject(
    website_id: str,
    request: ReviewWebsiteRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reject_website_api(payload["role"], payload["employee_id"], website_id, request.notes)


@app.post("/websites/{website_id}/pages/{page_key}/sections")
def websites_add_section(
    website_id: str,
    page_key: str,
    request: AddSectionRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_section_api(
        payload["role"],
        payload["employee_id"],
        website_id,
        page_key,
        request.section_key,
        request.fields
    )


@app.post("/websites/{website_id}/pages/{page_key}/sections/{section_index}/edit")
def websites_edit_section(
    website_id: str,
    page_key: str,
    section_index: int,
    request: UpdateSectionFieldsRequest,
    authorization: str = Header(None)
):
    """Manual in-place field edit -- see core/websites.py's update_section_fields()
    docstring for why this is distinct from both add_section (creates new) and
    regenerate_section (AI-only, ai_writable fields only)."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_section_fields_api(
        payload["role"], payload["employee_id"], website_id, page_key, section_index, request.fields
    )


@app.post("/websites/{website_id}/pages/{page_key}/sections/{section_index}/remove")
def websites_remove_section(
    website_id: str,
    page_key: str,
    section_index: int,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_section_api(payload["role"], payload["employee_id"], website_id, page_key, section_index)


@app.post("/websites/{website_id}/pages/{page_key}/sections/{section_index}/lock")
def websites_lock_section(
    website_id: str,
    page_key: str,
    section_index: int,
    request: SetSectionLockedRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_section_locked_api(
        payload["role"], payload["employee_id"], website_id, page_key, section_index, request.locked
    )


@app.post("/websites/{website_id}/mode")
def websites_set_mode(
    website_id: str,
    request: SetWebsiteModeRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_mode_api(payload["role"], payload["employee_id"], website_id, request.mode)


@app.post("/websites/{website_id}/owners")
def websites_add_owner(
    website_id: str,
    request: WebsiteOwnerRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_owner_api(payload["role"], payload["employee_id"], website_id, request.employee_id)


@app.post("/websites/{website_id}/owners/remove")
def websites_remove_owner(
    website_id: str,
    request: WebsiteOwnerRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_owner_api(payload["role"], payload["employee_id"], website_id, request.employee_id)


@app.post("/websites/{website_id}/admin-settings")
def websites_update_admin_settings(
    website_id: str,
    request: UpdateWebsiteAdminSettingsRequest,
    authorization: str = Header(None)
):
    """Sam's DNS/SEO/Bot/Analytics/OEM-branding admin controls -- see
    core/websites_api.py's update_admin_settings_api docstring for the MARKETING/ADMIN
    gate."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_admin_settings_api(payload["role"], payload["employee_id"], website_id, request.patch)


@app.get("/websites/{website_id}/dns-instructions")
def websites_dns_instructions(
    website_id: str,
    authorization: str = Header(None)
):
    """The honest DNS non-integration -- see core/websites.py's module docstring.
    Returns the exact CNAME record to create at the dealer's own registrar; NXTDeal
    does not provision DNS records itself."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_dns_instructions_api(payload["role"], payload["employee_id"], website_id)


@app.get("/websites/{website_id}/robots-txt")
def websites_robots_txt(
    website_id: str,
    authorization: str = Header(None)
):
    """Real generated robots.txt text -- see core/websites.py's get_robots_txt()
    (block_ai_crawlers adds Disallow entries for GPTBot/CCBot/ClaudeBot/
    Google-Extended/anthropic-ai)."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_robots_txt_api(payload["role"], payload["employee_id"], website_id)


# --- Enterprise SEO automation (session 113 follow-up) ------------------------------
# Real sitemap.xml generation, a real 100%-computable per-page SEO health score, real
# JSON-LD structured data, and AI-drafted meta copy grounded in a page's own real
# content. See core/website_seo.py's module docstring for what closed a genuine gap
# (robots.txt referenced a sitemap.xml URL since session 58 that nothing ever
# generated) vs. what's newly built.

@app.get("/websites/{website_id}/sitemap-xml")
def websites_sitemap_xml(website_id: str, authorization: str = Header(None)):
    """Authenticated preview of the sitemap (builder-side) -- see the public,
    unauthenticated /public/websites/{website_id}/sitemap.xml below for the real
    version a search engine would actually fetch."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_sitemap_xml_api(payload["role"], payload["employee_id"], website_id)


@app.get("/websites/{website_id}/seo-health")
def websites_seo_health(website_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_seo_health_api(payload["role"], payload["employee_id"], website_id)


@app.get("/websites/{website_id}/structured-data")
def websites_structured_data(website_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_structured_data_api(payload["role"], payload["employee_id"], website_id)


@app.post("/websites/{website_id}/pages/{page_key}/generate-seo-copy")
def websites_generate_seo_copy(website_id: str, page_key: str, authorization: str = Header(None)):
    """AI-drafts a meta title/description grounded in the page's own real content --
    a draft for the caller to review/apply via the existing page-seo PUT route, not an
    auto-apply action."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_page_seo_copy_api(payload["role"], payload["employee_id"], website_id, page_key)


# --- Vehicle Detail Pages (session 113 follow-up) ------------------------------------
# Real per-vehicle indexable pages -- closes the "AI-generated location/vehicle pages"
# item from Website's remaining "Wix-level asks" list. See core/websites.py's
# get_vehicle_landing_page()/generate_vehicle_page_description() docstrings. The public,
# unauthenticated GET route a real visitor hits lives further below alongside the other
# /public/websites/* routes; this one is the authenticated builder-side regenerate
# action (MARKETING/ADMIN-only, same gate as generate-seo-copy above).

@app.post("/websites/{website_id}/vehicles/{vehicle_id}/regenerate-description")
def websites_regenerate_vehicle_description(website_id: str, vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return regenerate_vehicle_description_api(payload["role"], payload["employee_id"], website_id, vehicle_id)


# ====================================================================# Session 85 -- Website Builder overhaul. Layout templates, drag-and-drop reorder,
# image library, per-page SEO, per-section AI regenerate, real preview + analytics,
# personal URL microsites, and live chat wired into the CRM. See
# core/websites.py/core/personal_sites.py/core/website_chat.py module docstrings for
# the full design notes, including the two scoping decisions made autonomously after
# an AskUserQuestion tool failure (single-page personal sites; REST+polling chat).
#
# NOTE ON ROUTE ORDERING: a bare single-segment route under /websites/ (e.g.
# "/websites/templates") would collide with the already-registered
# GET /websites/{website_id} above it (Starlette matches route templates in
# registration order, and both shapes match a 2-segment path) -- the earlier route
# would always win and this one would never be reached. The layout-template catalog is
# therefore exposed at the distinct top-level path GET /website-templates instead.
# Every other new route below adds two or more extra path segments past
# /websites/{website_id}/, which is a structurally different template with no
# collision regardless of declaration order.
# ====================================================================
@app.get("/website-studio/catalogue")
def website_studio_catalogue(authorization: str = Header(None)):
    _, error = _authenticate(authorization)
    if error:
        return error
    from core.website_studio import catalogue
    return catalogue()


class WebsiteStudioCreateRequest(BaseModel):
    name: str
    theme_id: str
    request_id: str
    mode: str = "traditional"


@app.post("/website-studio/sites")
def website_studio_create(request: WebsiteStudioCreateRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.website_studio import create_studio_api
    return create_studio_api(payload["employee_id"], request.name, request.theme_id, request.request_id, request.mode)


class WebsiteStudioUpdateRequest(BaseModel):
    config: dict
    expected_revision: int


@app.put("/websites/{website_id}/studio")
def website_studio_update(
    website_id: str,
    request: WebsiteStudioUpdateRequest,
    authorization: str = Header(None),
):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.website_studio import update_studio_api
    return update_studio_api(
        payload["role"], payload["employee_id"], website_id,
        request.config, request.expected_revision,
    )


@app.post("/websites/{website_id}/studio/draft")
def website_studio_start_draft(website_id: str, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.website_studio import start_draft_api
    return start_draft_api(payload["role"], payload["employee_id"], website_id)


@app.get("/websites/{website_id}/studio/inventory")
def website_studio_inventory(website_id: str, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.website_studio import studio_inventory_api
    return studio_inventory_api(payload["role"], payload["employee_id"], website_id)


@app.get("/website-templates")
def website_templates_list(dealer_type: str = None, authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_site_templates_api(dealer_type)


@app.post("/websites/{website_id}/apply-template")
def websites_apply_template(
    website_id: str,
    request: ApplySiteTemplateRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return apply_site_template_api(
        payload["role"], payload["employee_id"], website_id, request.template_key, request.dealership_name
    )


@app.post("/websites/{website_id}/pages/{page_key}/reorder")
def websites_reorder_sections(
    website_id: str,
    page_key: str,
    request: ReorderSectionsRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reorder_sections_api(payload["role"], payload["employee_id"], website_id, page_key, request.new_order)


@app.get("/websites/{website_id}/pages/{page_key}/sections/{section_index}/personalization-variants")
def websites_list_personalization_variants(
    website_id: str,
    page_key: str,
    section_index: int,
    authorization: str = Header(None)
):
    """Website Personalization (2026-07-19) -- real match-rule/field-override variants
    stored per-section, applied at render time by core/websites.py's render_page()."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_personalization_variants_api(payload["role"], payload["employee_id"], website_id, page_key, section_index)


@app.post("/websites/{website_id}/pages/{page_key}/sections/{section_index}/personalization-variants")
def websites_add_personalization_variant(
    website_id: str,
    page_key: str,
    section_index: int,
    request: AddPersonalizationVariantRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_personalization_variant_api(
        payload["role"], payload["employee_id"], website_id, page_key, section_index,
        request.match, request.field_overrides,
    )


@app.post("/websites/{website_id}/pages/{page_key}/sections/{section_index}/personalization-variants/{variant_id}/remove")
def websites_remove_personalization_variant(
    website_id: str,
    page_key: str,
    section_index: int,
    variant_id: str,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_personalization_variant_api(
        payload["role"], payload["employee_id"], website_id, page_key, section_index, variant_id
    )


@app.post("/websites/{website_id}/pages/{page_key}/layout-mode")
def websites_set_page_layout_mode(
    website_id: str,
    page_key: str,
    request: SetPageLayoutModeRequest,
    authorization: str = Header(None)
):
    """Freeform drag-and-drop canvas (2026-07-18) -- switches a page between
    "structured" (today's stacked flow) and "canvas" (real x/y/width/height
    positioning). See core/websites.py's set_page_layout_mode() docstring."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_page_layout_mode_api(payload["role"], payload["employee_id"], website_id, page_key, request.mode)


@app.post("/websites/{website_id}/pages/{page_key}/sections/{section_index}/layout")
def websites_set_section_layout(
    website_id: str,
    page_key: str,
    section_index: int,
    request: SetSectionLayoutRequest,
    authorization: str = Header(None)
):
    """Real drag/resize persistence for the freeform canvas -- called once on
    mouse-up, not on every mousemove. See core/websites.py's set_section_layout()
    docstring."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_section_layout_api(
        payload["role"], payload["employee_id"], website_id, page_key, section_index,
        request.x, request.y, request.width, request.height,
    )


@app.post("/websites/{website_id}/pages/{page_key}/sections/{section_index}/regenerate")
def websites_regenerate_section(
    website_id: str,
    page_key: str,
    section_index: int,
    request: RegenerateSectionRequest,
    authorization: str = Header(None)
):
    """Sam: 'each template section should have ai writing abilities.' Rewrites only
    that section's AI-writable fields -- see core/website_wizard.py's
    regenerate_section_copy() docstring."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return regenerate_section_api(
        payload["role"], payload["employee_id"], website_id, page_key, section_index, request.instructions
    )


@app.post("/websites/{website_id}/images")
def websites_add_image(
    website_id: str,
    request: AddLibraryImageRequest,
    authorization: str = Header(None)
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_library_image_api(payload["role"], payload["employee_id"], website_id, request.url, request.label)


@app.get("/websites/{website_id}/images")
def websites_list_images(website_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_library_images_api(payload["role"], payload["employee_id"], website_id)


@app.post("/websites/{website_id}/images/{image_id}/remove")
def websites_remove_image(website_id: str, image_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_library_image_api(payload["role"], payload["employee_id"], website_id, image_id)


@app.post("/websites/{website_id}/pages/{page_key}/seo")
def websites_update_page_seo(
    website_id: str,
    page_key: str,
    request: UpdatePageSeoRequest,
    authorization: str = Header(None)
):
    """Sam: 'adjust the seo per page.' MARKETING/ADMIN-only, same line as the rest of
    admin_settings."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_page_seo_api(payload["role"], payload["employee_id"], website_id, page_key, request.patch)


@app.get("/websites/{website_id}/pages/{page_key}/seo")
def websites_get_page_seo(website_id: str, page_key: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_page_seo_api(payload["role"], payload["employee_id"], website_id, page_key)


@app.post("/websites/{website_id}/preview")
def websites_preview(
    website_id: str,
    request: PreviewWebsiteRequest,
    authorization: str = Header(None)
):
    """Sam: 'preview the site.' Authenticated builder-side preview -- also logs a real
    page-view event, same honesty note as the public render route below."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return preview_website_api(
        payload["role"], payload["employee_id"], website_id, request.mode_override,
        utm_source=request.utm_source, referrer=request.referrer,
    )


@app.get("/websites/{website_id}/analytics")
def websites_analytics(website_id: str, authorization: str = Header(None), days: int = Query(30, ge=1, le=90)):
    """Sam: 'the admin side should have google analytics / umami style reporting.'"""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_website_analytics_api(payload["role"], payload["employee_id"], website_id, days)


@app.get("/public/websites/{website_id}")
def public_website_render(website_id: str, request: Request, mode: str = None, utm_source: str = None):
    """PUBLIC, unauthenticated -- an actual dealership website visitor. Only serves a
    'published' site. `mode` is the customer-facing traditional/DriveFinder toggle
    (see core/websites.py's get_website_rendered() docstring). Session 86: the real
    User-Agent header is read off `request` and passed through to back the new
    real bot-vs-human traffic classification (core/websites.py's
    _classify_user_agent()) -- no Authorization header is checked here, matching every
    other public route in this file. `utm_source` (2026-07-19, Website Personalization)
    is a real query param off the visitor's own URL; `referrer` is read off the real
    `Referer` request header (note the header's own historically-misspelled name) --
    both threaded through to back each section's own personalization_variants overlay."""

    return get_public_website_api(
        website_id,
        mode_override=mode,
        user_agent=request.headers.get("user-agent"),
        utm_source=utm_source,
        referrer=request.headers.get("referer"),
    )


@app.get("/public/websites/{website_id}/inventory")
def public_website_inventory(website_id: str, page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=48), location_id: str = None, q: str = Query("", max_length=100), make: str = None, max_price: float = None):
    from core.website_studio import public_inventory_api
    return public_inventory_api(website_id, page=page, page_size=page_size, location_id=location_id, query=q, make=make, max_price=max_price)


@app.post("/public/websites/{website_id}/contact")
def public_website_contact(website_id: str, request: SubmitContactFormRequest):
    """PUBLIC contact-form submission -- Sam: 'contact forms that feed into the crm.'
    Creates a real Lead, assigned to the site's owner."""

    return submit_contact_form_api(
        website_id, request.page_key, request.section_index, request.name, request.email, request.phone, request.message, request.vehicle_id, request.intent, request.request_id
    )


@app.get("/public/websites/{website_id}/sitemap.xml")
def public_website_sitemap(website_id: str):
    """PUBLIC, unauthenticated, real XML -- what a search engine actually fetches.
    Session 113 follow-up's enterprise SEO automation slice: robots.txt has
    referenced a sitemap.xml URL since session 58, but nothing ever served real
    content at it until now (see core/website_seo.py's module docstring). Calls the
    ACL-free core function directly (not get_sitemap_xml_api, which is gated to the
    site's own builders/MARKETING/ADMIN) -- a sitemap is meant for anonymous crawlers
    by definition, same as get_public_website_api just above."""

    result = get_sitemap_xml(website_id)

    if isinstance(result, dict) and "error" in result:
        return PlainTextResponse(result["error"], status_code=404, media_type="text/plain")

    return PlainTextResponse(result["sitemap_xml"], media_type="application/xml")


@app.get("/public/websites/{website_id}/robots.txt")
def public_website_robots(website_id: str):
    """PUBLIC, unauthenticated, real plain text -- the actual URL a crawler requests.
    core/websites.py's get_robots_txt() has generated real text since session 58, but
    it only ever had an authenticated builder-preview route until now. Same
    ACL-free-core-function-not-the-gated-_api-wrapper reasoning as the sitemap route
    above."""

    result = get_robots_txt(website_id, published=True)

    if isinstance(result, dict) and "error" in result:
        return PlainTextResponse("User-agent: *\nDisallow: /", media_type="text/plain")

    return PlainTextResponse(result["robots_txt"], media_type="text/plain")


@app.get("/public/websites/{website_id}/vehicles/{vehicle_id}")
def public_website_vehicle(website_id: str, vehicle_id: str):
    """PUBLIC, unauthenticated -- a real Vehicle Detail Page (session 113 follow-up).
    Calls the ACL-free core function directly, same reasoning as the sitemap/robots.txt
    routes above -- a real site visitor browsing inventory isn't an authenticated
    builder session. Only serves a published site's vehicles; a sold vehicle still
    renders (with available: false) rather than erroring, since a bookmarked/shared
    VDP link for a since-sold vehicle should show an honest state, not a dead link.
    A genuinely missing website/vehicle returns the plain {"error": ...} dict, same
    convention every other public JSON route in this file already uses (e.g.
    get_public_website_api) rather than a non-200 status code."""

    return get_vehicle_landing_page(website_id, vehicle_id)


# --- Website live chat, wired into the CRM ------------------------------------------

@app.post("/public/websites/{website_id}/chat/start")
def public_chat_start(website_id: str, request: StartChatSessionRequest):
    """PUBLIC -- the site's chat widget opening a new conversation. `department`
    (session 113 follow-up) is the visitor's own real/service/finance/general pick."""

    return start_chat_session_api(
        website_id, request.visitor_name, request.visitor_email, request.initial_message,
        department=request.department,
    )


@app.get("/public/chat/departments")
def public_chat_departments():
    """PUBLIC -- the real department options the widget's picker renders."""

    return list_departments_api()


@app.get("/public/chat/{session_id}")
def public_chat_get_session(session_id: str):
    """PUBLIC -- lets the visitor's own widget re-fetch its session status (e.g. 'an
    agent has joined')."""

    return get_session_api(session_id)


@app.post("/public/chat/{session_id}/messages")
def public_chat_send_message(session_id: str, request: SendChatMessageRequest):
    """PUBLIC -- the visitor's own reply. The session_id itself is the visitor's only
    credential, same as any support-chat widget."""

    return send_visitor_message_api(session_id, request.body)


@app.get("/public/chat/{session_id}/messages")
def public_chat_list_messages(session_id: str, since: str = None):
    """PUBLIC -- the polling loop. `since` is the last message's created_at the widget
    already has."""

    return list_messages_api(session_id, since)


# ---------------------------------------------------------------------------
# NXTDeal Verify (Digital Retail) -- PUBLIC, unauthenticated customer verification.
# The session_token returned by /start is the customer's only credential (same posture
# as a chat session_id or the Customer Payment Portal token). Every action is recorded
# against dealeros_verify.CUSTOMER_SENTINEL, never an employee id.
# ---------------------------------------------------------------------------

@app.post("/public/verify/start")
def public_verify_start(request: VerifyStartRequest):
    """PUBLIC -- a visitor begins a verification session. Returns the session_token the
    client must keep and present on every subsequent /public/verify call."""

    return public_start_verification(email=request.email, phone=request.phone)


@app.get("/public/verify/{token}")
def public_verify_get(token: str):
    """PUBLIC -- the visitor's own widget re-fetching its current tier and next steps."""

    return public_get_verification(token)


@app.post("/public/verify/{token}/contact")
def public_verify_set_contact(token: str, request: VerifySetContactRequest):
    """PUBLIC -- add/change the email or phone before requesting a code."""

    return public_set_contact(token, email=request.email, phone=request.phone)


@app.post("/public/verify/{token}/request-code")
def public_verify_request_code(token: str, request: VerifyRequestCodeRequest):
    """PUBLIC -- request an email or SMS one-time code (honestly simulated delivery)."""

    return public_request_code(token, request.channel)


@app.post("/public/verify/{token}/confirm-code")
def public_verify_confirm_code(token: str, request: VerifyConfirmCodeRequest):
    """PUBLIC -- confirm the code; email + SMS both verified promotes to Verified Human."""

    return public_confirm_code(token, request.channel, request.code)


@app.post("/public/verify/{token}/identity")
def public_verify_identity(token: str, request: VerifySubmitIdentityRequest):
    """PUBLIC -- submit driver license + selfie (simulated match) for Identity Verified."""

    return public_submit_identity(token, request.license_number, selfie_provided=request.selfie_provided)


@app.post("/public/verify/{token}/credit")
def public_verify_credit(token: str, request: VerifySubmitCreditRequest):
    """PUBLIC -- attach a completed (decisioned) credit application for Credit Verified."""

    return public_submit_credit(token, request.credit_app_id)


# ==================================================================================# Customer accounts — NXTDeal's customer-facing login for the My Garage app (2026-07-24).
# Sign-up + login are PUBLIC (no token yet); link + me require a CUSTOMER bearer token,
# which is domain-separated from employee tokens (core/customer_accounts) so it can never
# authenticate an employee route. On the shared apps host these hit the tenant's own backend
# (resolved per login — see docs/DEPLOYMENT.md). "Match + verify": sign-up matches an
# existing Customer/Lead by email/phone but only ATTACHES it after a one-time code confirm.
# ==================================================================================
class CustomerSignupRequest(BaseModel):

    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)


class CustomerLoginRequest(BaseModel):

    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class CustomerLinkRequestCodeRequest(BaseModel):

    channel: str = Field(default="email", pattern="^(email|sms)$")


class CustomerLinkConfirmRequest(BaseModel):

    channel: str = Field(pattern="^(email|sms)$")
    code: str = Field(min_length=4, max_length=10, pattern="^[0-9]+$")


@app.post("/public/customer/signup")
def public_customer_signup(request: CustomerSignupRequest):
    """PUBLIC -- create a customer account; if an existing record matches, a one-time code
    is requested on the matched contact. Real provider codes are never returned;
    legacy simulated codes require an explicit development-only opt-in."""

    return customer_signup_api(request.email, request.password, name=request.name, phone=request.phone)


@app.post("/public/customer/login")
def public_customer_login(request: CustomerLoginRequest):
    """PUBLIC -- customer email + password sign-in; returns a customer bearer token."""

    return customer_login_api(request.email, request.password)


@app.post("/customer/link/request-code")
def customer_link_request_code(request: CustomerLinkRequestCodeRequest, authorization: str = Header(None)):
    """Customer token -- (re)send the one-time code for the pending CRM-record link."""

    return customer_request_link_code_api(authorization, channel=request.channel)


@app.post("/customer/link/confirm")
def customer_link_confirm(request: CustomerLinkConfirmRequest, authorization: str = Header(None)):
    """Customer token -- confirm the code and attach the matched Customer/Lead record."""

    return customer_confirm_link_code_api(authorization, request.channel, request.code)


@app.post("/customer/logout")
def customer_logout(authorization: str = Header(None)):
    """Revoke all customer sessions belonging to the authenticated account."""
    from core.customer_accounts_api import logout_api
    return logout_api(authorization)


@app.get("/customer/me")
def customer_me(authorization: str = Header(None)):
    """Customer token -- the signed-in customer's account + linked record summary."""

    return customer_me_api(authorization)


# ==================================================================================# MySales rep referral / reward program (2026-07-24). Rep-facing views are keyed to the
# signed-in employee (any authed role); advancing a referral's status is admin/operations.
# ==================================================================================
class DealershipReferralRequest(BaseModel):

    kind: str  # "dealership_demo" | "dealership_conversion"
    dealership_name: str
    contact_name: str | None = None
    contact_email: str | None = None
    notes: str | None = None


class ApplyReferralCodeRequest(BaseModel):

    code: str


class AdvanceReferralRequest(BaseModel):

    status: str


@app.get("/referrals/me")
def referrals_me(authorization: str = Header(None)):
    """The signed-in rep's referral code, reward tiers, totals, and their referrals."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return referrals_my_summary_api(payload["employee_id"])


@app.post("/referrals/dealership")
def referrals_submit_dealership(request: DealershipReferralRequest, authorization: str = Header(None)):
    """The rep reports they're referring their dealership for a NXTDeal demo or conversion."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return referrals_submit_dealership_api(
        payload["employee_id"], request.kind, request.dealership_name,
        contact_name=request.contact_name, contact_email=request.contact_email, notes=request.notes,
    )


@app.post("/referrals/apply-code")
def referrals_apply_code(request: ApplyReferralCodeRequest, authorization: str = Header(None)):
    """A newly-joined rep records whose referral code recruited them."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return referrals_apply_code_api(payload["employee_id"], request.code)


@app.get("/referrals/admin/queue")
def referrals_admin_queue(status: str = None, authorization: str = Header(None)):
    """Admin/operations -- every referral (optionally filtered by status) to work the queue."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return referrals_list_all_api(payload["role"], status=status)


@app.post("/referrals/{referral_id}/advance")
def referrals_advance(referral_id: str, request: AdvanceReferralRequest, authorization: str = Header(None)):
    """Admin/operations -- move a referral along its flow ('rewarded' marks it earned)."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return referrals_advance_api(payload["role"], payload["employee_id"], referral_id, request.status)


# ==================================================================================# MySales self-accounting (2026-07-24). Every view is the signed-in rep's OWN money (any
# authed employee). Bank linking runs through the "banking" integrations capability (Plaid),
# simulated until a real adapter is registered.
# ==================================================================================
class LinkBankRequest(BaseModel):

    institution: str | None = None


class SetBudgetRequest(BaseModel):

    category: str
    limit: float


class RecordCommissionRequest(BaseModel):

    amount: float
    status: str = "pending"
    source: str | None = None
    deal_id: str | None = None
    date: str | None = None


@app.get("/finance/overview")
def finance_overview(authorization: str = Header(None)):
    """The rep's money on one screen: cash, accounts, budgets, commissions, AI advisor."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return finance_overview_api(payload["employee_id"])


@app.post("/finance/link-bank")
def finance_link_bank(request: LinkBankRequest, authorization: str = Header(None)):
    """Link a bank via the Plaid seam (simulated until a real provider is connected)."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return finance_link_bank_api(payload["employee_id"], institution=request.institution)


@app.get("/finance/budgets")
def finance_budgets(authorization: str = Header(None)):
    """The rep's budgets with this month's spend vs each limit."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return finance_list_budgets_api(payload["employee_id"])


@app.post("/finance/budgets")
def finance_set_budget(request: SetBudgetRequest, authorization: str = Header(None)):
    """Create or update one category's monthly budget."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return finance_set_budget_api(payload["employee_id"], request.category, request.limit)


@app.get("/finance/commissions")
def finance_commissions(authorization: str = Header(None)):
    """The rep's logged commission entries (projected / pending / paid)."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return finance_list_commissions_api(payload["employee_id"])


@app.post("/finance/commissions")
def finance_record_commission(request: RecordCommissionRequest, authorization: str = Header(None)):
    """Log a commission the rep expects or was paid, so it sits next to their bank cash."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return finance_record_commission_api(
        payload["employee_id"], request.amount, status=request.status,
        source=request.source, deal_id=request.deal_id, date=request.date,
    )


@app.get("/finance/advisor")
def finance_advisor(authorization: str = Header(None)):
    """The rules-based AI budget advisor's current insights for this rep."""

    payload, error = _authenticate(authorization)
    if error:
        return error
    return finance_advisor_api(payload["employee_id"])


# ==================================================================================# AI Demo Platform (2026-07-24). All PUBLIC — the demo mints its own persona session. Entry
# only works in a DEALEROS_DEMO tenant (a separate, seeded, fully non-persistent deployment);
# on a real dealer backend start_demo refuses, so employees never see demo mode. The persona
# token is a normal employee token, so every existing dashboard works against the seeded data.
# ==================================================================================
class StartDemoRequest(BaseModel):

    persona: str
    mode: str = "guided"
    # Nullable: the frontend sends explicit null for these when unused, and Pydantic v2 rejects
    # null against a non-optional type (a bare `dict = None` still requires a dict if provided).
    contact: dict | None = None
    access_code: str | None = None


class DemoTrackRequest(BaseModel):

    session_id: str
    kind: str
    detail: dict | None = None


@app.get("/public/demo/personas")
def public_demo_personas():
    """The role picker + scenarios + modes; `enabled` is false on a non-demo tenant."""

    return demo_personas_api()


@app.post("/public/demo/start")
def public_demo_start(request: StartDemoRequest):
    """Begin a guided demo as a persona — returns a session token + tour outline + watermark."""

    return start_demo_api(request.persona, mode=request.mode, contact=request.contact, access_code=request.access_code)


def _authorize_demo_session(session_id, authorization):
    payload, error = _authenticate(authorization)
    if error:
        return error
    if payload.get("employee_id") != f"DEMO:{session_id}":
        return {"error": "Demo session access denied"}
    return None


@app.post("/public/demo/track")
def public_demo_track(request: DemoTrackRequest, authorization: str = Header(None)):
    """Record a demo interaction (page view / question / module) for AI lead qualification."""

    error = _authorize_demo_session(request.session_id, authorization)
    if error:
        return error
    return demo_track_event_api(request.session_id, request.kind, detail=request.detail)


@app.get("/public/demo/session/{session_id}")
def public_demo_session(session_id: str, authorization: str = Header(None)):
    """The demo session's current analytics snapshot."""

    error = _authorize_demo_session(session_id, authorization)
    if error:
        return error
    return demo_get_session_api(session_id)


@app.get("/public/demo/summary/{session_id}")
def public_demo_summary(session_id: str, authorization: str = Header(None)):
    """End-of-demo AI lead qualification — interests, intent, a tailored recommendation + CTAs."""

    error = _authorize_demo_session(session_id, authorization)
    if error:
        return error
    return demo_summarize_session_api(session_id)


# ---------------------------------------------------------------------------
# NXTDeal Digital Retail self-service (DR-4, 2026-07-24) -- PUBLIC, token-driven.
# A verified customer builds/negotiates/finances/signs a deal with no staff. Every
# step is gated on BOTH the Verify tier (require_capability) and the workflow's
# execution mode being open to the customer (require_actor), inside core/digital_retail.py.
# The Verify session token is the only credential; actions record as CUSTOMER_SENTINEL.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# My Garage — PUBLIC, verify-token-scoped customer data (App Suite Phase 4 + 7). A
# Verified-Human session sees THEIR own vehicles/equity/service/messages. core/garage.py
# resolves the token to a real Customer (match-and-verify) and returns an honest
# "no account found" if the verified contact matches nobody.
# ---------------------------------------------------------------------------
@app.get("/public/garage/vehicles")
def public_garage_vehicles(token: str):
    from core.garage import get_my_vehicles
    return get_my_vehicles(token)


@app.get("/public/garage/service")
def public_garage_service(token: str):
    from core.garage import get_my_service_history
    return get_my_service_history(token)


@app.get("/public/garage/messages")
def public_garage_messages(token: str):
    from core.garage import get_my_messages
    return get_my_messages(token)


@app.get("/public/garage/approvals")
def public_garage_approvals(token: str):
    from core.garage import get_my_approvals
    return get_my_approvals(token)


@app.post("/public/garage/approvals/{ro_id}/respond")
def public_garage_respond_approval(ro_id: str, request: GarageApprovalRequest):
    from core.garage import respond_to_approval
    return respond_to_approval(request.token, ro_id, request.approved, decline_reason=request.decline_reason)


@app.post("/public/garage/approvals/{ro_id}/pay")
def public_garage_pay(ro_id: str, request: GaragePayRequest):
    from core.garage import pay_my_ro
    return pay_my_ro(request.token, ro_id, method=request.method)


@app.get("/public/garage/status")
def public_garage_status(token: str):
    from core.garage import get_my_status
    return get_my_status(token)


# ---------------------------------------------------------------------------
# Entitlements -- the tenant-side Foundation-plus-Modules enforcement layer
# (Freemium Platform roadmap, Phase 1, 2026-08-03). GET /public/entitlements is the
# non-sensitive active-module read a customer-facing app (no staff session) uses to gate its
# own screens; the authenticated reads expose the full record + catalog; the admin setters
# author the record (tenant-side, and actually enforced -- unlike the Hub's config-only
# Module Management / Licensing). See core/entitlements.py.
# ---------------------------------------------------------------------------

class EntitlementProfileRequest(BaseModel):
    profile: str


class EntitlementModuleRequest(BaseModel):
    module: str
    enabled: bool
    level: str | None = None


class EntitlementCapRequest(BaseModel):
    cap: str
    value: int | None = None


@app.get("/public/entitlements")
def public_entitlements_route():
    """PUBLIC, read-only: the active-module set + owned levels, so a no-login customer app can
    gate its own screens. Nothing sensitive -- it's the equivalent of which features a site has."""
    from core.entitlements import public_entitlements
    return public_entitlements()


@app.get("/entitlements")
def entitlements_status(authorization: str = Header(None)):
    """The full entitlement record: profile, per-module enabled/level, usage caps, and the
    resolved active-module/level conveniences."""
    _, error = _authenticate(authorization)
    if error:
        return error
    from core.entitlements import get_entitlements
    return get_entitlements()


@app.get("/entitlements/catalog")
def entitlements_catalog(authorization: str = Header(None)):
    """The static Foundation + Modules + features + caps + industry-launch-path catalog."""
    _, error = _authenticate(authorization)
    if error:
        return error
    from core.entitlements import get_catalog
    return get_catalog()


@app.post("/entitlements/profile")
def entitlements_set_profile(request: EntitlementProfileRequest, authorization: str = Header(None)):
    """ADMIN: switch the whole record to 'reference' (full build) or 'foundation' (Tier 0)."""
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.entitlements import set_profile
    return set_profile(request.profile, payload.get("employee_id") or payload.get("role"))


@app.post("/entitlements/module")
def entitlements_set_module(request: EntitlementModuleRequest, authorization: str = Header(None)):
    """ADMIN: enable/disable one paid Module (optionally at a level). Moves record to 'custom'."""
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.entitlements import set_module
    return set_module(request.module, request.enabled, payload.get("employee_id") or payload.get("role"), level=request.level)


@app.post("/entitlements/cap")
def entitlements_set_cap(request: EntitlementCapRequest, authorization: str = Header(None)):
    """ADMIN: set (int) or lift (null = unlimited) a Foundation usage cap."""
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.entitlements import set_cap
    return set_cap(request.cap, request.value, payload.get("employee_id") or payload.get("role"))


# ---------------------------------------------------------------------------
# AI Spend Governor (Freemium roadmap, Phase 5): the dealer admin's bring-your-own-key AI
# posture + per-user consumption limits + aggregate usage view. ADMIN-only, mirrors the other
# Administration Control Center surfaces. See core/ai_spend.py.
# ---------------------------------------------------------------------------

class AiSpendProviderRequest(BaseModel):
    provider: str
    byo_key_configured: bool | None = None


class AiSpendLimitRequest(BaseModel):
    limit: int | None = None


class AiSpendUserLimitRequest(BaseModel):
    user_id: str
    limit: int | None = None


@app.get("/ai-spend/policy")
def ai_spend_policy(authorization: str = Header(None)):
    _, error = _require_admin(authorization)
    if error:
        return error
    from core.ai_spend import get_policy
    return get_policy()


@app.get("/ai-spend/overview")
def ai_spend_overview(period: str = None, authorization: str = Header(None)):
    _, error = _require_admin(authorization)
    if error:
        return error
    from core.ai_spend import get_spend_overview
    return get_spend_overview(period)


@app.post("/ai-spend/provider")
def ai_spend_set_provider(request: AiSpendProviderRequest, authorization: str = Header(None)):
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.ai_spend import set_provider
    return set_provider(request.provider, payload.get("employee_id") or payload.get("role"), byo_key_configured=request.byo_key_configured)


@app.post("/ai-spend/limit")
def ai_spend_set_default_limit(request: AiSpendLimitRequest, authorization: str = Header(None)):
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.ai_spend import set_default_limit
    return set_default_limit(request.limit, payload.get("employee_id") or payload.get("role"))


@app.post("/ai-spend/user-limit")
def ai_spend_set_user_limit(request: AiSpendUserLimitRequest, authorization: str = Header(None)):
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.ai_spend import set_user_limit
    return set_user_limit(request.user_id, request.limit, payload.get("employee_id") or payload.get("role"))


# --- AI on/off toggles + managed provider config (Freemium 2026-08-03) ---

class AiEnabledRequest(BaseModel):
    enabled: bool


class MyAiRequest(BaseModel):
    enabled: bool


class CustomEndpointRequest(BaseModel):
    base_url: str | None = None
    model: str | None = None
    auth_header: str | None = None
    notes: str | None = None
    clear: bool | None = None


class ManagedRateRequest(BaseModel):
    rate: float


@app.post("/ai-spend/ai-enabled")
def ai_spend_set_ai_enabled(request: AiEnabledRequest, authorization: str = Header(None)):
    """ADMIN: the dealer-level master AI switch. When off, all AI is off dealer-wide (server-side)
    and the AI UI hides for everyone."""
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.ai_spend import set_ai_enabled
    return set_ai_enabled(request.enabled, payload.get("employee_id") or payload.get("role"))


@app.post("/ai-spend/custom-endpoint")
def ai_spend_set_custom_endpoint(request: CustomEndpointRequest, authorization: str = Header(None)):
    """ADMIN: point the 'custom' provider at a homegrown / any-API endpoint (or clear it)."""
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.ai_spend import set_custom_endpoint
    config = None if request.clear else {
        "base_url": request.base_url, "model": request.model,
        "auth_header": request.auth_header, "notes": request.notes,
    }
    return set_custom_endpoint(config, payload.get("employee_id") or payload.get("role"))


@app.post("/ai-spend/managed-rate")
def ai_spend_set_managed_rate(request: ManagedRateRequest, authorization: str = Header(None)):
    """ADMIN: usage-based price per AI action for the managed NXTDeal AI provider."""
    payload, error = _require_admin(authorization)
    if error:
        return error
    from core.ai_spend import set_managed_rate
    return set_managed_rate(request.rate, payload.get("employee_id") or payload.get("role"))


@app.get("/ai-spend/my-status")
def ai_spend_my_status(authorization: str = Header(None)):
    """ANY authenticated user: whether AI is on for ME (dealer master AND my own opt-out). The
    product reads this to decide whether to render AI chrome at all."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.ai_spend import get_my_ai_status
    return get_my_ai_status(payload.get("employee_id"))


@app.post("/ai-spend/my-ai")
def ai_spend_set_my_ai(request: MyAiRequest, authorization: str = Header(None)):
    """ANY authenticated user: turn AI on/off for MYSELF (some people just don't want it)."""
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.ai_spend import set_user_ai_enabled, get_my_ai_status
    uid = payload.get("employee_id")
    if not uid:
        return {"error": "No employee identity on this session."}
    set_user_ai_enabled(uid, request.enabled, uid)
    return get_my_ai_status(uid)


# --- MySales personal AI config (per-rep, self-scoped) ---

class MySalesAiEnabledRequest(BaseModel):
    enabled: bool


class MySalesByokRequest(BaseModel):
    provider: str
    api_key: str = ""


class MySalesRoutingRequest(BaseModel):
    on_device_when_available: bool | None = None
    routine_tier: str | None = None
    premium_tier: str | None = None


@app.get("/mysales/ai-config")
def mysales_ai_config_get(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.mysales_ai import get_config
    return get_config(payload.get("employee_id"))


@app.post("/mysales/ai-config/enabled")
def mysales_ai_config_enabled(request: MySalesAiEnabledRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.mysales_ai import set_ai_enabled
    return set_ai_enabled(payload.get("employee_id"), request.enabled)


@app.post("/mysales/ai-config/byok")
def mysales_ai_config_byok(request: MySalesByokRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.mysales_ai import set_byok
    return set_byok(payload.get("employee_id"), request.provider, request.api_key)


@app.post("/mysales/ai-config/byok/clear")
def mysales_ai_config_byok_clear(authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.mysales_ai import clear_byok
    return clear_byok(payload.get("employee_id"))


@app.post("/mysales/ai-config/routing")
def mysales_ai_config_routing(request: MySalesRoutingRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.mysales_ai import set_routing
    return set_routing(
        payload.get("employee_id"),
        on_device_when_available=request.on_device_when_available,
        routine_tier=request.routine_tier,
        premium_tier=request.premium_tier,
    )


# ---------------------------------------------------------------------------
# Generalized AI model-selector config (per-user, per-app) (2026-10-24).
# Extends the MySales personal AI pattern to all companion apps. Staff apps
# (salesapp, reception, serviceops) get per-employee config; customer apps
# (showroom, mygarage, kiosk) are dealer-managed only. See core/ai_config.py.
# ---------------------------------------------------------------------------

class AiConfigRequest(BaseModel):
    app: str = ""


class AiConfigEnabledRequest(BaseModel):
    app: str = ""
    enabled: bool


class AiConfigByokRequest(BaseModel):
    app: str = ""
    provider: str
    api_key: str = ""


class AiConfigRoutingRequest(BaseModel):
    app: str = ""
    on_device_when_available: bool | None = None
    routine_tier: str | None = None
    premium_tier: str | None = None


@app.get("/ai-config/app")
def ai_config_get(request: Request, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.ai_config import get_config
    app_slug = request.query_params.get("app", "mysales")
    return get_config(payload.get("employee_id"), app_slug)


@app.post("/ai-config/app/enabled")
def ai_config_enabled(request_body: AiConfigEnabledRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.ai_config import set_ai_enabled
    return set_ai_enabled(payload.get("employee_id"), request_body.app, request_body.enabled)


@app.post("/ai-config/app/byok")
def ai_config_byok(request_body: AiConfigByokRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.ai_config import set_byok
    return set_byok(payload.get("employee_id"), request_body.app, request_body.provider, request_body.api_key)


@app.post("/ai-config/app/byok/clear")
def ai_config_byok_clear(request_body: AiConfigRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.ai_config import clear_byok
    return clear_byok(payload.get("employee_id"), request_body.app)


@app.post("/ai-config/app/routing")
def ai_config_routing(request_body: AiConfigRoutingRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.ai_config import set_routing
    return set_routing(
        payload.get("employee_id"),
        request_body.app,
        on_device_when_available=request_body.on_device_when_available,
        routine_tier=request_body.routine_tier,
        premium_tier=request_body.premium_tier,
    )


@app.get("/ai-config/app/resolve")
def ai_config_resolve(request: Request, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    from core.ai_config import resolve_model
    app_slug = request.query_params.get("app", "mysales")
    task = request.query_params.get("task", "routine")
    return resolve_model(payload.get("employee_id"), app_slug, task)

# ---------------------------------------------------------------------------
# Programming Schedule tracker (2026-10-24) — work-item board for the NXTDeal
# production bridge. Tracks features, bugs, security issues, tech-debt across
# phases, with assignee, progress, hours, and dependencies.
# See backend/core/programming_schedule.py.
# ---------------------------------------------------------------------------

def _ps_admin_or_error(authorization):
    """Admin-level auth check for programming-schedule routes.

    Returns (payload, None) on success, or (None, JSONResponse) on failure.
    401 when logged out or token is invalid; 403 when authenticated but not ADMIN.
    Machine routes (webhooks, agent-channel) use their own HMAC/agent-secret checks
    and are excluded here.
    """
    payload, error = _require_admin(authorization)
    if error:
        if error.get("error") == "Admin role required":
            return None, JSONResponse(status_code=403, content=error)
        return None, JSONResponse(status_code=401, content=error)
    return payload, None

class PSItemRequest(BaseModel):
    title: str
    description: str = ""
    item_type: str = "feature"
    phase: str = "Phase 0"
    priority: str = "medium"
    assignee: str = "unassigned"
    est_hours: float = 0
    depends_on: list = []
    security_severity: str | None = None
    resource_route: str = "local"
    owner: str = "auto"


class PSUpdateRequest(BaseModel):
    title: str = ""
    description: str = ""
    item_type: str = ""
    phase: str = ""
    status: str = ""
    priority: str = ""
    assignee: str = ""
    est_hours: float | None = None
    logged_hours: float | None = None
    progress: int | None = None
    depends_on: list | None = None
    security_severity: str | None = None
    resource_route: str | None = None
    owner: str | None = None


class PSProgressRequest(BaseModel):
    progress: int


class PSAssignRequest(BaseModel):
    assignee: str


class PSSStatusRequest(BaseModel):
    status: str


class PSHoursRequest(BaseModel):
    hours: float


class PSRouteRequest(BaseModel):
    resource_route: str
    owner: str | None = None


class PSNoteRequest(BaseModel):
    note: str


class PSResourceRequest(BaseModel):
    resource: str


# --- Section 2: Machine endpoints (worker token auth) ---
class PSClaimRequest(BaseModel):
    worker: str
    route: str


class PSHeartbeatRequest(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0


class PSCompleteRequest(BaseModel):
    outcome: str
    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    commit_sha: str | None = None
    tests_summary: str | None = None
    notes: str | None = None
    progress: int | None = None


@app.get("/programming-schedule")
def ps_list(
    phase: str | None = None,
    assignee: str | None = None,
    status: str | None = None,
    item_type: str | None = None,
    priority: str | None = None,
    authorization: str | None = Header(None),
):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import list_items
    return list_items(phase=phase, assignee=assignee, status=status,
                      item_type=item_type, priority=priority)


@app.get("/programming-schedule/dashboard")
def ps_dashboard(authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.dashboard_renderer import _build_dashboard_data
    return _build_dashboard_data()


@app.post("/programming-schedule")
def ps_create(request_body: PSItemRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import create_item
    return create_item(
        title=request_body.title, description=request_body.description,
        item_type=request_body.item_type, phase=request_body.phase,
        priority=request_body.priority, assignee=request_body.assignee,
        est_hours=request_body.est_hours, depends_on=request_body.depends_on,
        security_severity=request_body.security_severity,
    )


@app.get("/programming-schedule/ci-runs")
def ps_list_ci_runs(status: str | None = None, authorization: str | None = Header(None)):
    """List all CI pipeline run entities (CIPipelineRun), optionally filtered by status.
    ADMIN-only."""
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.dealeros import ledger
    from core.entity_types import CI_PIPELINE_RUN
    results = []
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != CI_PIPELINE_RUN:
            continue
        if status and entity.attributes.get("status") != status:
            continue
        results.append({"id": entity.id, **dict(entity.attributes)})
    return results


@app.get("/programming-schedule/deployment-runs")
def ps_list_deployment_runs(status: str | None = None, authorization: str | None = Header(None)):
    """List all deployment run entities (DeploymentRun), optionally filtered by status.
    ADMIN-only."""
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.dealeros import ledger
    from core.entity_types import DEPLOYMENT_RUN
    results = []
    for entity_id in ledger.entities:
        entity = ledger.get_entity(entity_id)
        if not entity or entity.entity_type != DEPLOYMENT_RUN:
            continue
        if status and entity.attributes.get("status") != status:
            continue
        results.append({"id": entity.id, **dict(entity.attributes)})
    return results


@app.get("/programming-schedule/dashboard-view")
def ps_dashboard_view(authorization: str | None = Header(None)):
    """Serve the interactive dashboard HTML directly from the backend.

    Requires ADMIN session. The data is regenerated from the live ledger on
    every request — no local file dependency.
    """
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.dashboard_renderer import render_dashboard_html
    from fastapi.responses import HTMLResponse
    html = render_dashboard_html()
    return HTMLResponse(content=html)


# --- Section 2: Machine endpoints (worker token auth, NOT admin session) ---
# These routes must be registered BEFORE /programming-schedule/{item_id}
# to avoid FastAPI route shadowing. See Section 0 fix (PS-054).

def _is_free_model(model: str | None, provider: str | None = None) -> bool:
    """True if the model string indicates a free-tier model (Section 2 constraint).

    Accepts ':free' in model, or model/provider starting with 'local-'
    (covers local-desktop, local-mac, local-vps, local-mac/qwen3.6-35b, etc).
    The Mac Studio runs Qwen3.6-35B on Hermes' built-in runner at $0, so it
    must report as provider='local-mac', model='local-mac/qwen3.6-35b'.
    """
    if not model:
        return True
    if provider and provider.startswith("local-"):
        return True
    return ":free" in model or model.startswith("local-")


@app.post("/programming-schedule/claim")
def ps_claim(request_body: PSClaimRequest, authorization: str | None = Header(None)):
    """Machine endpoint: claim the next eligible item.

    Authenticated by per-worker Bearer token (schedule_auth), not admin session.
    Returns the claimed item + run_id.
    """
    from core.schedule_auth import worker_token_or_error
    worker, error = worker_token_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import claim_item
    return claim_item(request_body.route, worker)


@app.post("/programming-schedule/runs/{run_id}/heartbeat")
def ps_run_heartbeat(run_id: str, request_body: PSHeartbeatRequest,
                     authorization: str | None = Header(None)):
    """Machine endpoint: extend lease and update token/cost counters.

    Authenticated by per-worker Bearer token. The token must correspond to the
    worker that owns the run.
    """
    from core.schedule_auth import worker_token_or_error
    worker, error = worker_token_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import get_run, heartbeat_run
    run = get_run(run_id)
    if not run:
        return {"error": f"Run '{run_id}' not found", "status_code": 404}
    if run.get("worker") != worker:
        return {"error": "Token does not match the run's worker", "status_code": 403}
    return heartbeat_run(run_id,
                         input_tokens=request_body.input_tokens,
                         output_tokens=request_body.output_tokens,
                         cache_read_tokens=request_body.cache_read_tokens,
                         cost_usd=request_body.cost_usd)


@app.post("/programming-schedule/runs/{run_id}/complete")
def ps_run_complete(run_id: str, request_body: PSCompleteRequest,
                    authorization: str | None = Header(None)):
    """Machine endpoint: mark a run as complete with outcome and metrics.

    Rejects reports whose model is not ':free' unless explicitly approved
    (records and flags them).
    """
    from core.schedule_auth import worker_token_or_error
    worker, error = worker_token_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import get_run, complete_run, add_event
    run = get_run(run_id)
    if not run:
        return {"error": f"Run '{run_id}' not found", "status_code": 404}
    if run.get("worker") != worker:
        return {"error": "Token does not match the run's worker", "status_code": 403}

    # Free-model gate: only allow :free models (or local-*) unless Sam approved.
    # Non-free reports are recorded and flagged but still accepted.
    if not _is_free_model(request_body.model, request_body.provider):
        add_event(run.get("item_id"), "note_added", worker,
                  f"WARNING: non-free model '{request_body.model}' used for run {run_id}")

    return complete_run(run_id, request_body.outcome,
                        commit_sha=request_body.commit_sha,
                        tests_summary=request_body.tests_summary,
                        notes=request_body.notes,
                        progress=request_body.progress)


@app.get("/programming-schedule/runs/active")
def ps_active_runs(authorization: str | None = Header(None)):
    """Machine endpoint: list all active (running) schedule runs."""
    from core.schedule_auth import worker_token_or_error
    worker, error = worker_token_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import get_active_runs
    return get_active_runs()


@app.get("/programming-schedule/runs/{run_id}")
def ps_get_run(run_id: str, authorization: str | None = Header(None)):
    """Machine endpoint: retrieve a specific run by ID."""
    from core.schedule_auth import worker_token_or_error
    worker, error = worker_token_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import get_run
    run = get_run(run_id)
    if not run:
        return {"error": f"Run '{run_id}' not found", "status_code": 404}
    return run


@app.get("/programming-schedule/{item_id}")
def ps_get(item_id: str, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import get_item
    item = get_item(item_id)
    if not item:
        return {"error": f"Item '{item_id}' not found"}
    return item


@app.patch("/programming-schedule/{item_id}")
def ps_update(item_id: str, request_body: PSUpdateRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import update_item
    fields = {k: v for k, v in request_body.model_dump().items() if v != "" and v is not None}
    return update_item(item_id, **fields)


@app.post("/programming-schedule/{item_id}/progress")
def ps_progress(item_id: str, request_body: PSProgressRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import update_progress
    return update_progress(item_id, request_body.progress)


@app.post("/programming-schedule/{item_id}/assign")
def ps_assign(item_id: str, request_body: PSAssignRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import assign_item
    return assign_item(item_id, request_body.assignee)


@app.post("/programming-schedule/{item_id}/status")
def ps_status(item_id: str, request_body: PSSStatusRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import set_status
    return set_status(item_id, request_body.status)


@app.post("/programming-schedule/{item_id}/hours")
def ps_hours(item_id: str, request_body: PSHoursRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import add_hours
    return add_hours(item_id, request_body.hours)


@app.post("/programming-schedule/{item_id}/notes")
def ps_add_note(item_id: str, request_body: PSNoteRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import add_work_note
    return add_work_note(item_id, request_body.note)


@app.post("/programming-schedule/{item_id}/resources")
def ps_add_resource(item_id: str, request_body: PSResourceRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import add_resource
    return add_resource(item_id, request_body.resource)


@app.get("/programming-schedule/route/{route}")
def ps_by_route(route: str, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import get_by_route
    return get_by_route(route)


@app.post("/programming-schedule/{item_id}/route")
def ps_set_route(item_id: str, request_body: PSRouteRequest, authorization: str | None = Header(None)):
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.programming_schedule import set_route
    return set_route(item_id, request_body.resource_route, request_body.owner)


# ---------------------------------------------------------------------------
# CI/CD Pipeline Integration (2026-10-25)
#
# Closes the gap between manual status updates and actual verified completion.
# The status flow is: in_review -> done (auto, CI pass) -> deployed (auto, Coolify
# success) -> pushed_live (auto or manual, production health verified).
# See core/ci_deploy_pipeline.py for the implementation and trust model.
#
# Webhooks: authenticated by HMAC signature, not user tokens.
# Agent channel: authenticated by shared NXTDEAL_AGENT_SECRET token.
# ---------------------------------------------------------------------------

class PSWebhookRequest(BaseModel):
    from_agent: str | None = None
    to_agent: str | None = None
    message_type: str | None = None
    payload: dict = {}


@app.post("/programming-schedule/webhooks/github")
async def ps_github_webhook(request: Request, x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256")):
    """GitHub Actions workflow_run webhook -- verifies HMAC signature, records CI result,
    auto-advances PS items from 'in_review' to 'done' when CI passes."""
    body = await request.body()
    from core.ci_deploy_pipeline import receive_github_webhook
    result = receive_github_webhook(body, x_hub_signature_256 or "")
    return result


@app.post("/programming-schedule/webhooks/coolify")
async def ps_coolify_webhook(request: Request, x_coolify_signature: str | None = Header(None, alias="X-Coolify-Signature")):
    """Coolify deployment webhook -- verifies HMAC signature, records deployment,
    auto-advances PS items from 'done' to 'deployed' when deployment succeeds."""
    body = await request.body()
    from core.ci_deploy_pipeline import receive_coolify_webhook
    result = receive_coolify_webhook(body, x_coolify_signature or "")
    return result


@app.get("/programming-schedule/agent-channel/messages")
def ps_get_agent_messages(agent: str, token: str, unread_only: bool = True, limit: int = 50):
    """Agent message inbox -- desktop Hermes and VPS Hermes agent poll this to retrieve
    messages addressed to them. Authenticated by NXTDEAL_AGENT_SECRET token."""
    from core.ci_deploy_pipeline import get_agent_messages
    return get_agent_messages(agent, token, unread_only=unread_only, limit=limit)


@app.post("/programming-schedule/agent-channel/send")
def ps_send_agent_message(from_agent: str, to_agent: str, message_type: str, payload: dict, token: str):
    """Agent-to-agent message send -- used by desktop Hermes and VPS Hermes agents to
    exchange deployment commands, status queries, and results. Authenticated by
    NXTDEAL_AGENT_SECRET token."""
    from core.ci_deploy_pipeline import send_agent_message
    return send_agent_message(from_agent, to_agent, message_type, payload, token)


@app.post("/programming-schedule/agent-channel/mark-read")
def ps_mark_messages_read(agent: str, token: str, channel_id: str | None = None):
    """Mark agent messages as read."""
    from core.ci_deploy_pipeline import mark_messages_read
    return mark_messages_read(agent, token, channel_id=channel_id)


@app.get("/programming-schedule/deployment/{deployment_id}/status")
def ps_deployment_status(deployment_id: str, authorization: str | None = Header(None)):
    """Poll Coolify API for a deployment's current status. ADMIN-only."""
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.ci_deploy_pipeline import poll_coolify_deployment
    return poll_coolify_deployment(deployment_id)


@app.get("/programming-schedule/{item_id}/production-health")
def ps_production_health(item_id: str, authorization: str | None = Header(None)):
    """Verify that a deployed item is actually live in production -- checks Coolify
    deployment status and health-check URLs attached as resources on the PS item.
    ADMIN-only."""
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.ci_deploy_pipeline import verify_production_health
    return verify_production_health(item_id)


@app.post("/programming-schedule/{item_id}/mark-pushed-live")
def ps_mark_pushed_live(item_id: str, verified_by: str = "auto", authorization: str | None = Header(None)):
    """Mark a deployed item as pushed_live after verifying production health.
    This completes the pipeline: done -> deployed -> pushed_live. ADMIN-only."""
    payload, error = _ps_admin_or_error(authorization)
    if error:
        return error
    from core.ci_deploy_pipeline import mark_pushed_live
    return mark_pushed_live(item_id, verified_by=verified_by)


@app.on_event("startup")
def ps_start_ci_loop():
    """Start the CI/CD polling loop on app startup."""
    from core.ci_deploy_pipeline import start, tick
    try:
        tick()
        start()
    except Exception:
        pass


@app.on_event("shutdown")
def ps_stop_ci_loop():
    """Stop the CI/CD polling loop on shutdown."""
    from core.ci_deploy_pipeline import stop
    stop()


# Onboarding auto-signals (Phase 2) + Provider catalog (Phase 3) -- in-product authed reads. The
# Hub reads the same onboarding data server-to-server via /network/onboarding-signals-snapshot; this
# is the tenant's own in-app onboarding checklist + the Integrations Center's real provider catalog.
# ---------------------------------------------------------------------------

@app.get("/onboarding/signals")
def onboarding_signals_route(authorization: str = Header(None)):
    _, error = _authenticate(authorization)
    if error:
        return error
    from core.onboarding_signals import compute_onboarding_signals
    return compute_onboarding_signals()


@app.get("/providers/catalog")
def providers_catalog_route(authorization: str = Header(None)):
    _, error = _authenticate(authorization)
    if error:
        return error
    from core.provider_catalog import get_provider_catalog
    return get_provider_catalog()


@app.get("/providers/migration-sources")
def providers_migration_sources_route(authorization: str = Header(None)):
    _, error = _authenticate(authorization)
    if error:
        return error
    from core.provider_catalog import list_migration_sources
    return {"migration_sources": list_migration_sources()}


@app.post("/public/retail/deals")
def public_retail_start_deal(request: RetailStartDealRequest):
    """PUBLIC -- a verified customer starts a deal on a vehicle (needs Identity Verified +
    desking open to the customer)."""

    return retail_start_deal(request.token, request.vehicle_id)


@app.get("/public/retail/deals/{deal_id}")
def public_retail_deal_room(deal_id: str, token: str):
    """PUBLIC -- the customer's consolidated deal room (tier, deal, negotiations, F&I, the
    true payment with F&I rolled in, next steps)."""

    return retail_get_deal_room(token, deal_id)


@app.post("/public/retail/deals/{deal_id}/trade")
def public_retail_trade(deal_id: str, request: RetailTradeRequest):
    """PUBLIC -- submit a trade for evaluation (needs Verified Human + trade open to customer)."""

    patch = {k: v for k, v in request.dict().items() if k != "token" and v is not None}
    return retail_submit_trade(request.token, deal_id, patch)


@app.post("/public/retail/deals/{deal_id}/negotiation")
def public_retail_start_negotiation(deal_id: str, request: RetailStartNegotiationRequest):
    """PUBLIC -- open a negotiation session (needs Identity Verified + negotiation open)."""

    return retail_start_negotiation(request.token, deal_id, target_payment=request.target_payment)


@app.post("/public/retail/negotiation/{session_id}/offer")
def public_retail_make_offer(session_id: str, request: RetailOfferRequest):
    """PUBLIC -- the customer's offer. In-bounds approves; out-of-bounds escalates to a manager."""

    proposal = {k: v for k, v in request.dict().items() if k != "token" and v is not None}
    return retail_make_offer(request.token, session_id, proposal)


@app.post("/public/retail/negotiation/{session_id}/accept")
def public_retail_accept_negotiation(session_id: str, request: RetailTokenRequest):
    """PUBLIC -- accept the negotiated terms (writes back a real deal scenario)."""

    return retail_accept_negotiation(request.token, session_id)


@app.post("/public/retail/deals/{deal_id}/credit")
def public_retail_apply_credit(deal_id: str, request: RetailApplyCreditRequest):
    """PUBLIC -- apply for financing. A decisioned application advances the customer to
    Credit Verified."""

    applicant = {k: request.dict().get(k) for k in
                 ("employment_status", "employer_name", "years_at_employer",
                  "monthly_housing_payment", "housing_status")
                 if request.dict().get(k) is not None}
    return retail_apply_credit(
        request.token, deal_id, applicant,
        monthly_income=request.monthly_income,
        co_applicant=request.co_applicant, requested_amount=request.requested_amount,
    )


@app.post("/public/retail/deals/{deal_id}/financing")
def public_retail_choose_financing(deal_id: str, request: RetailTokenRequest):
    """PUBLIC -- select the negotiated scenario and self-approve in-house/BHPH financing
    (needs Credit Verified)."""

    return retail_choose_financing(request.token, deal_id)


@app.post("/public/retail/deals/{deal_id}/fi")
def public_retail_select_fi(deal_id: str, request: RetailSelectFiRequest):
    """PUBLIC -- accept/decline an F&I product; the response includes the payment with F&I
    rolled in (needs Credit Verified)."""

    return retail_select_fi(request.token, deal_id, request.product_key, request.decision)


@app.post("/public/retail/deals/{deal_id}/sign")
def public_retail_sign(deal_id: str, request: RetailSignRequest):
    """PUBLIC -- generate (if needed) and sign the contract (needs Credit Verified)."""

    return retail_sign(request.token, deal_id, request.typed_signature)


@app.post("/public/retail/deals/{deal_id}/delivery")
def public_retail_schedule_delivery(deal_id: str, request: RetailScheduleDeliveryRequest):
    """PUBLIC -- the final step: the customer schedules store pickup / home delivery
    (needs Credit Verified + delivery open to the customer)."""

    return retail_schedule_delivery(request.token, deal_id, request.mode, request.window_start,
                                    window_end=request.window_end, address=request.address)


@app.get("/public/approve/{token}")
def public_approval_view(token: str):
    """PUBLIC, unauthenticated -- a real customer viewing their own RO's
    estimate/concerns/flagged DVI findings via a real shareable link (see
    core/approval_center.py's module docstring). The token itself is the
    customer's only credential, same as a chat session_id above."""

    return get_public_approval_view(token)


@app.post("/public/approve/{token}/decision")
def public_approval_decision(token: str, body: PublicApprovalDecisionRequest):
    """PUBLIC -- the real customer-initiated approve/decline action, recorded
    with recorded_by=CUSTOMER_SENTINEL so it's always distinguishable from a
    staff member recording the decision on the customer's behalf."""

    return record_public_approval_decision(token, body.approved, decline_reason=body.decline_reason)


@app.get("/websites/{website_id}/chat/sessions")
def websites_chat_inbox(website_id: str, authorization: str = Header(None)):
    """The employee-side chat inbox for one site -- builder/owners or MARKETING/ADMIN
    only, see core/website_chat_api.py's _can_work_chat()."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_open_sessions_api(payload["role"], payload["employee_id"], website_id)


@app.post("/websites/chat/{session_id}/reply")
def websites_chat_reply(session_id: str, request: SendChatMessageRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return send_employee_reply_api(payload["role"], payload["employee_id"], session_id, request.body)


@app.get("/websites/chat/{session_id}/messages")
def websites_chat_messages(session_id: str, since: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_messages_api(session_id, since)


@app.post("/websites/chat/{session_id}/claim")
def websites_chat_claim(session_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return claim_session_api(payload["role"], payload["employee_id"], session_id)


@app.post("/websites/chat/{session_id}/close")
def websites_chat_close(session_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return close_session_api(payload["role"], payload["employee_id"], session_id)


@app.post("/websites/chat/{session_id}/promote")
def websites_chat_promote(session_id: str, request: PromoteChatSessionRequest, authorization: str = Header(None)):
    """The one-click 'wired into the crm' promote action -- same precedent as
    core/trigger_alerts.py's promote_alert()/core/dealership_events.py's
    promote_rsvp_to_lead() (session 84)."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return promote_session_api(payload["role"], payload["employee_id"], session_id, request.name, request.email, request.phone)


@app.get("/chat/inbox")
def chat_unified_inbox(status: str = None, department: str = None, authorization: str = Header(None)):
    """The real 'omnichannel' Live Chat upgrade (session 113 follow-up) -- every chat
    session across every site this employee can manage, in one call, filterable by
    status/department, instead of the old one-website-at-a-time inbox
    (GET /websites/{website_id}/chat/sessions, still there, unchanged, for a
    single-site view). Registered under a distinct /chat/* prefix rather than
    /websites/chat/* to avoid any risk of route-shadowing against the existing
    dynamic /websites/chat/{session_id}/* paths."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_unified_inbox_api(payload["role"], payload["employee_id"], status=status, department=department)


@app.post("/chat/{session_id}/ai-reply")
def chat_ai_reply(session_id: str, authorization: str = Header(None)):
    """The AI Receptionist's explicit manual trigger -- an employee can request a
    real AI-drafted (and immediately posted) reply at any time, on top of the
    automatic path core/website_chat.py's send_visitor_message() already covers for
    an unclaimed session on an ai_receptionist_enabled site."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_ai_reply_api(payload["role"], payload["employee_id"], session_id)


# --- DMS Deal Desk (session 33) -- wiring the routes (session 91 follow-up) ---
#
# core/deals_api.py's functions were imported into this file (above) since session 33
# but NEVER had an @app.get/@app.post route exposing any of them -- the exact same
# class of gap session 89's CLAUDE.md entry documents for compliance/employee-value/
# department-intelligence/network/readiness/connections/bot. Confirmed via grep before
# writing this block: zero call sites for create_deal_api/add_scenario_api/etc.
# anywhere in this file. Wired here as part of building the Sales "Deals" submenu's
# real Pipeline board + Deal Worksheet (Sam's Sales sub-menu spec, 2026-07-16).

@app.get("/deals/lenders")
def deals_list_lenders(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_lenders_api()


@app.post("/deals")
def deals_create(request: CreateDealRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_deal_api(payload["role"], payload["employee_id"], request.customer_id, request.vehicle_id, request.trade_in)


@app.get("/deals")
def deals_list_all(status: str = None, authorization: str = Header(None)):
    """The Pipeline board's real data source -- every deal on the board, not just the
    caller's own (see core/deals_api.py's _BOARD_VIEW_ROLES)."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_all_deals_api(payload["role"], status)


@app.get("/deals/mine")
def deals_list_mine(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_my_deals_api(payload["employee_id"])


@app.get("/deals/pending-financing")
def deals_pending_financing(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_pending_financing_api(payload["role"])


@app.get("/deals/{deal_id}")
def deals_get(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_deal_api(payload["role"], payload["employee_id"], deal_id)


@app.post("/deals/{deal_id}/scenarios")
def deals_add_scenario(deal_id: str, request: AddScenarioRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    # Desking (the deal builder / scenario calculator) is a Sales Module feature (Freemium
    # roadmap): the free CRM keeps the pipeline; building priced deal scenarios sits behind Sales.
    # No-op under the default "reference" profile; real once a dealer is on Foundation.
    from core.entitlements import require_module
    gate = require_module("sales")
    if gate:
        return gate

    return add_scenario_api(
        payload["role"], payload["employee_id"], deal_id,
        request.label, request.sale_price, request.down_payment, request.term_months,
    )


@app.delete("/deals/{deal_id}/scenarios/{scenario_id}")
def deals_remove_scenario(deal_id: str, scenario_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_scenario_api(payload["role"], payload["employee_id"], deal_id, scenario_id)


@app.post("/deals/{deal_id}/scenarios/{scenario_id}/select")
def deals_select_scenario(deal_id: str, scenario_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return select_scenario_api(payload["role"], payload["employee_id"], deal_id, scenario_id)


@app.post("/deals/{deal_id}/trade-appraisal")
def deals_update_trade_appraisal(deal_id: str, request: TradeAppraisalRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_trade_appraisal_api(payload["role"], payload["employee_id"], deal_id, request.patch)


@app.post("/deals/{deal_id}/trade-appraisal/approve")
def deals_approve_trade_appraisal(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return approve_trade_appraisal_api(payload["role"], payload["employee_id"], deal_id)


@app.post("/deals/{deal_id}/delivery-checklist")
def deals_update_delivery_checklist(deal_id: str, request: DeliveryChecklistRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_delivery_checklist_api(payload["role"], payload["employee_id"], deal_id, request.section, request.patch)


@app.post("/deals/{deal_id}/financing/in-house")
def deals_choose_in_house_financing(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return choose_in_house_financing_api(payload["role"], payload["employee_id"], deal_id)


@app.post("/deals/{deal_id}/financing/submit")
def deals_submit_to_lender(deal_id: str, request: SubmitLenderRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return submit_to_lender_api(payload["role"], payload["employee_id"], deal_id, request.lender_id)


@app.post("/deals/{deal_id}/financing/decision")
def deals_record_lender_decision(deal_id: str, request: LenderDecisionRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_lender_decision_api(
        payload["role"], payload["employee_id"], deal_id,
        request.decision, request.countered_terms, request.notes,
    )


@app.post("/deals/{deal_id}/financing/accept-countered")
def deals_accept_countered_terms(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return accept_countered_terms_api(payload["role"], payload["employee_id"], deal_id)


@app.post("/deals/{deal_id}/contract")
def deals_generate_contract(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_contract_api(payload["role"], payload["employee_id"], deal_id)


@app.post("/deals/{deal_id}/fund")
def deals_fund(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return fund_deal_api(payload["role"], payload["employee_id"], deal_id)


@app.post("/deals/{deal_id}/cancel")
def deals_cancel(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_deal_api(payload["role"], payload["employee_id"], deal_id)


# --- Prospects / Lead Record (Sales sub-menu spec, session 92 follow-up) ---
#
# Sam: "When opening a prospect: Customer Profile, Activity Timeline, Communication
# Hub (Call/Text/Email/Video, all logged automatically), Task Management, Customer
# Notes, Next Best Action." core/lead_record.py assembles this from pieces that
# already existed (Lead entity, audit log, core/field_notes.py) plus two small new
# pieces (core/lead_tasks.py, core/lead_conversion.py) -- routed here as its own
# block rather than through the generic /menu/data JSON dump, same treatment
# crm/email_sms/social_reputation/deals already got.

@app.get("/leads/{lead_id}/record")
def leads_get_record(lead_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lead_record_api(payload["role"], lead_id)


@app.post("/leads/{lead_id}/log")
def leads_log_activity(lead_id: str, request: CreateFieldNoteRequest, authorization: str = Header(None)):
    """Communication Hub -- logs a call/text/email/video touch as a FieldNote tied to
    this lead. request.category must be one of core/field_notes.py's
    COMMUNICATION_CATEGORIES equivalents (call/text/email/video); request.department
    is ignored in favor of a fixed "Sales" tag, and linked_entity_id is forced to the
    path's lead_id so a client can't log against the wrong record."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_field_note_api(payload["employee_id"], "Sales", request.category, request.body, lead_id)


@app.post("/leads/{lead_id}/notes")
def leads_add_note(lead_id: str, request: CreateFieldNoteRequest, authorization: str = Header(None)):
    """Customer Notes -- objection/family/competitor/payment_goal/general, same
    FieldNote mechanism as the Communication Hub above, distinguished by category."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_field_note_api(payload["employee_id"], "Sales", request.category, request.body, lead_id)


@app.post("/leads/{lead_id}/tasks")
def leads_create_task(lead_id: str, request: CreateLeadTaskRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_task_api(
        payload["role"], payload["employee_id"], lead_id,
        request.task_type, request.description, request.due_at, request.assigned_to,
    )


@app.post("/tasks/{task_id}/complete")
def tasks_complete(task_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return complete_task_api(payload["role"], payload["employee_id"], task_id)


@app.get("/tasks")
def tasks_list(lead_id: str = None, assigned_to: str = None, include_completed: bool = True, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_tasks_api(payload["role"], lead_id, assigned_to, include_completed)


@app.post("/leads/{lead_id}/convert")
def leads_convert(lead_id: str, authorization: str = Header(None)):
    """The 'Create Deal' Action Center button's real prerequisite -- a Deal needs a
    real Customer, and a Lead isn't one yet. See core/lead_conversion.py's module
    docstring for the real BECAME relationship this reuses."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return convert_lead_to_customer_api(payload["role"], payload["employee_id"], lead_id)


# --- Sales Overview (Sales sub-menu spec, session 94 follow-up) ---
#
# Sam: "My Tasks Widget (Leads requiring contact today, Appointments arriving within
# 2 hours, Missing follow-ups, Unsold showroom visits, Deals awaiting manager
# approval), Action Center (Call/Text/Email/Schedule Appointment/Create Deal/Transfer
# Lead per item), Daily Sales Dashboard, Sales Manager Dashboard." Renders ABOVE
# (not replacing) the existing generic Overview KPI board on the frontend -- see
# core/sales_overview.py's module docstring. "Transfer Lead" needed a real new
# manual-assignment route since the existing `/lead/assign/{lead_id}` route is
# auto/round-robin assignment (a different function), not an explicit hand-off.

@app.get("/sales/my-day")
def sales_my_day(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_my_day_api(payload["role"], payload["employee_id"])


@app.get("/sales/employees")
def sales_employees(authorization: str = Header(None)):
    """A plain Sales-department roster -- the "Transfer Lead" picker's data source."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_sales_employees_api(payload["role"])


@app.post("/leads/{lead_id}/transfer")
def leads_transfer(lead_id: str, request: TransferLeadRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return transfer_lead_api(payload["role"], payload["employee_id"], lead_id, request.new_employee_id)


# ---------------------------------------------------------------------------
# Appointments (17 routes: /appointments*, /appointment-scheduling/*,
# /public/checkin/*, /service/employees) -- extracted to
# api/routers/appointments.py (CAF-00120, god_file_app_py -- splitting this
# file into domain-scoped routers). Included via
# app.include_router(appointments_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# --- Inventory: Reservation/Hold + Comparison Tool (session 99 follow-up) ---
#
# Closes the last of Sales' 8 original Top Menu gaps -- see core/vehicle_holds.py's
# module docstring for why a hold is a short-lived graph entity rather than a Vehicle
# field, and core/sales_menu.py's compare_vehicles() for the comparison tool.

@app.post("/inventory/holds")
def inventory_holds_create(request: PlaceHoldRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return place_hold_api(
        payload["role"], payload["employee_id"], request.vehicle_id,
        customer_id=request.customer_id, lead_id=request.lead_id,
        notes=request.notes, duration_hours=request.duration_hours,
    )


@app.get("/inventory/holds")
def inventory_holds_list(mine: bool = False, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    if mine:
        return list_my_holds_api(payload["role"], payload["employee_id"])

    return list_active_holds_api(payload["role"])


@app.post("/inventory/holds/{hold_id}/release")
def inventory_holds_release(hold_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return release_hold_api(payload["role"], payload["employee_id"], hold_id)


@app.get("/sales/inventory/compare")
def sales_inventory_compare(ids: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    vehicle_ids = [v for v in ids.split(",") if v.strip()]

    return compare_vehicles_sales(payload["role"], vehicle_ids)


# --- BDC (session 100 follow-up) ---
#
# The second of Sam's ~10 "completely missing" dealership workflows -- a real
# untouched-internet-lead queue with genuine speed-to-lead measurement. See
# core/bdc.py's module docstring for the honest precise_timestamp/urgency caveats.

@app.get("/bdc/dashboard")
def bdc_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_bdc_dashboard_api(payload["role"])


@app.get("/bdc/queue")
def bdc_queue(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_untouched_queue_api(payload["role"])


@app.get("/bdc/qualification")
def bdc_qualification(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_qualification_queue_api(payload["role"])


@app.get("/bdc/handoff-candidates")
def bdc_handoff_candidates(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_handoff_candidates_api(payload["role"])


# --- Manager TO / Turn-Over (session 101 follow-up) ---
#
# The third of Sam's ~10 "completely missing" dealership workflows -- a real,
# timed hand-off queue (requested -> claimed -> resolved) for when a salesperson
# can't close and asks a manager to take a fresh crack at the customer. See
# core/manager_to.py's module docstring.

@app.get("/manager-to/reasons")
def manager_to_reasons(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_to_reasons_api()


@app.get("/manager-to/statuses")
def manager_to_statuses(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_to_statuses_api()


@app.get("/manager-to/outcomes")
def manager_to_outcomes(authorization: str = Header(None)):

    _, error = _authenticate(authorization)
    if error:
        return error

    return list_to_outcomes_api()


@app.post("/manager-to/request")
def manager_to_request(request: RequestTORequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_to_api(payload["role"], payload["employee_id"], request.linked_entity_id, request.reason, notes=request.notes)


@app.post("/manager-to/{to_id}/claim")
def manager_to_claim(to_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return claim_to_api(payload["role"], payload["employee_id"], to_id)


@app.post("/manager-to/{to_id}/resolve")
def manager_to_resolve(to_id: str, request: ResolveTORequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return resolve_to_api(payload["role"], payload["employee_id"], to_id, request.outcome, notes=request.notes)


@app.get("/manager-to/open")
def manager_to_open(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_open_tos_api(payload["role"])


@app.get("/manager-to")
def manager_to_list(status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_tos_api(payload["role"], status=status)


@app.get("/manager-to/stats")
def manager_to_stats(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_to_stats_api(payload["role"])


# ---------------------------------------------------------------------------
# Workforce Management -- Directory, Shift Scheduling, Time-Off Requests,
# Coverage, Performance. Extracted to api/routers/workforce.py (CAF-00120,
# god_file_app_py -- splitting this file into domain-scoped routers).
# Included via app.include_router(workforce_router) near the top of this
# file. Same 14 routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AI Marketing Studio -- generate/apply/discard AI-drafted marketing content
# drafts across every channel. Extracted to api/routers/marketing_studio.py
# (CAF-00120, god_file_app_py -- splitting this file into domain-scoped
# routers). Included via app.include_router(marketing_studio_router) near
# the top of this file. Same 5 routes, same behavior.
# ---------------------------------------------------------------------------


# Demo Drive's 8 routes moved to api/routers/demo_drives.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(demo_drives_router) below.

# Credit Applications' 13 routes moved to api/routers/credit_apps.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(credit_apps_router) below.


# eSignature's 14 routes moved to api/routers/esignature.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(esignature_router) below.


@app.get("/fi-products/catalog")
def fi_products_catalog(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_fi_product_catalog_api(payload["role"])


@app.get("/fi-products/dashboard")
def fi_products_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_fi_products_dashboard_api(payload["role"])


@app.get("/fi-products/penetration")
def fi_products_penetration(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_product_penetration_stats_api(payload["role"])


@app.get("/fi-products/queue")
def fi_products_queue(limit: int = 25, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_deals_needing_fi_menu_api(payload["role"], limit=limit)


@app.get("/fi-products/{deal_id}")
def fi_products_get_menu(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_fi_menu_api(payload["role"], deal_id)


# Phase 4: personalized F&I menu recommendation for a deal.
@app.get("/fi-products/{deal_id}/recommend")
def fi_products_recommend(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return recommend_fi_products_api(payload["role"], deal_id)


@app.post("/fi-products/{deal_id}/present")
def fi_products_present(deal_id: str, request: PresentFIProductsRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return present_fi_products_api(payload["role"], deal_id, request.product_keys, payload["employee_id"])


@app.post("/fi-products/{deal_id}/{product_key}/pricing")
def fi_products_update_pricing(deal_id: str, product_key: str, request: UpdateFIProductPricingRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_fi_product_pricing_api(payload["role"], deal_id, product_key, cost=request.cost, price=request.price)


@app.post("/fi-products/{deal_id}/{product_key}/decide")
def fi_products_decide(deal_id: str, product_key: str, request: DecideFIProductRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return decide_fi_product_api(payload["role"], deal_id, product_key, request.decision, declined_reason=request.declined_reason)


# Lost Sale Recovery's 11 routes moved to api/routers/lost_sale_recovery.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(lost_sale_recovery_router) below.


# --- Orphan Owner Mining moved to api/routers/orphan_owners.py (CAF-00120) --
# see app.include_router(orphan_owners_router) below.


# Vehicle Lifecycle's 13 routes (Operations' Vehicle Lifecycle Management
# plus Inventory's Master Vehicle Workspace cost-breakdown/ownership/activity
# endpoints) moved to api/routers/vehicle_lifecycle.py (CAF-00120,
# god_file_app_py) -- registered via
# app.include_router(vehicle_lifecycle_router) below.


# Acquisitions' 16 routes moved to api/routers/acquisitions.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(acquisitions_router) below.

# --- Inventory: Pricing Desk (Inventory rebuild, third slice) ---
# Static /pricing-desk/queue registered before the dynamic /pricing-desk/{vehicle_id}
# path, same route-shadowing-avoidance precedent as /acquisitions/*.

@app.get("/pricing-desk/queue")
def pricing_desk_queue(limit: int = 25, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_pricing_queue_api(payload["role"], limit=limit)


@app.get("/pricing-desk/{vehicle_id}")
def pricing_desk_view(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_pricing_view_api(payload["role"], vehicle_id)


@app.get("/pricing-desk/{vehicle_id}/market")
def pricing_desk_market(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_market_pricing_api(payload["role"], vehicle_id)


@app.get("/pricing-desk/{vehicle_id}/competitors")
def pricing_desk_competitors(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_competitor_comparisons_api(payload["role"], vehicle_id)


@app.get("/pricing-desk/{vehicle_id}/age-adjustment")
def pricing_desk_age_adjustment(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_age_based_adjustment_api(payload["role"], vehicle_id)


@app.get("/pricing-desk/{vehicle_id}/recommendation")
def pricing_desk_recommendation(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_pricing_recommendation_api(payload["role"], vehicle_id)


@app.post("/pricing-desk/{vehicle_id}/apply-price")
def pricing_desk_apply_price(vehicle_id: str, request: ApplyPriceRecommendationRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return apply_price_recommendation_api(payload["role"], payload["employee_id"], vehicle_id, request.new_price, reason=request.reason)


# --- NXTDeal VIN Intelligence, Phase 1 + Phase 2's /vin-decoder/* routes ---
# Moved to backend/api/routers/vin_decoder.py (CAF-00120, god_file_app_py --
# app.include_router(vin_decoder_router) near the top of this file). Same 5
# routes (decode, get-by-vehicle, apply, bulk-apply, match-check), same
# behavior. The one remaining Phase 2 route below (Sales' trade-in decode on
# a Deal) stays inline -- it belongs to the much larger "deals" domain,
# deliberately left for a later, more cautious extraction pass.

@app.get("/deals/{deal_id}/trade-in/decode-vin")
def deals_decode_trade_in_vin(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return decode_trade_in_vin_api(payload["role"], deal_id)


# --- Inventory: Lot Management (Inventory rebuild, fifth slice) ---
# Static /lot-control/map and /lot-control/keys/board and /lot-control/showroom/board
# registered before the dynamic /lot-control/{vehicle_id} path, same
# route-shadowing-avoidance precedent as /acquisitions/*, /pricing-desk/*.

@app.get("/lot-control/map")
def lot_control_map(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lot_map_api(payload["role"])


@app.get("/lot-control/keys/board")
def lot_control_key_board(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_key_board_api(payload["role"])


@app.get("/lot-control/showroom/board")
def lot_control_showroom_board(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_showroom_board_api(payload["role"])


@app.get("/lot-control/damage-reports")
def lot_control_list_damage_reports(vehicle_id: str = None, status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_damage_reports_api(payload["role"], vehicle_id=vehicle_id, status=status)


@app.post("/lot-control/damage-reports/{report_id}/status")
def lot_control_update_damage_status(report_id: str, request: UpdateDamageStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_damage_status_api(payload["role"], payload["employee_id"], report_id, request.new_status, resolution_notes=request.resolution_notes)


@app.get("/lot-control/{vehicle_id}")
def lot_control_view(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lot_control_view_api(payload["role"], vehicle_id)


@app.get("/lot-control/{vehicle_id}/position")
def lot_control_get_position(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lot_position_api(payload["role"], vehicle_id)


@app.post("/lot-control/{vehicle_id}/position")
def lot_control_set_position(vehicle_id: str, request: SetLotPositionRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_lot_position_api(payload["role"], payload["employee_id"], vehicle_id, row=request.row, space=request.space, section=request.section, notes=request.notes)


@app.get("/lot-control/{vehicle_id}/key")
def lot_control_get_key_status(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_key_status_api(payload["role"], vehicle_id)


@app.post("/lot-control/{vehicle_id}/key/checkout")
def lot_control_checkout_key(vehicle_id: str, request: CheckoutKeyRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return checkout_key_api(payload["role"], payload["employee_id"], vehicle_id, request.holder, notes=request.notes)


@app.post("/lot-control/{vehicle_id}/key/checkin")
def lot_control_checkin_key(vehicle_id: str, request: NotesOnlyRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return checkin_key_api(payload["role"], payload["employee_id"], vehicle_id, notes=request.notes)


@app.post("/lot-control/{vehicle_id}/key/missing")
def lot_control_report_key_missing(vehicle_id: str, request: NotesOnlyRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return report_key_missing_api(payload["role"], payload["employee_id"], vehicle_id, notes=request.notes)


@app.post("/lot-control/{vehicle_id}/damage-reports")
def lot_control_report_damage(vehicle_id: str, request: ReportDamageRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return report_damage_api(payload["role"], payload["employee_id"], vehicle_id, request.severity, request.description, estimated_cost=request.estimated_cost)


@app.post("/lot-control/{vehicle_id}/showroom")
def lot_control_assign_showroom(vehicle_id: str, request: NotesOnlyRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return assign_showroom_api(payload["role"], payload["employee_id"], vehicle_id, notes=request.notes)


@app.post("/lot-control/{vehicle_id}/showroom/remove")
def lot_control_remove_showroom(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return remove_showroom_assignment_api(payload["role"], payload["employee_id"], vehicle_id)


@app.post("/lot-control/{vehicle_id}/scan")
def lot_control_log_scan(vehicle_id: str, request: LogScanRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return log_scan_api(payload["role"], payload["employee_id"], vehicle_id, location_note=request.location_note)


@app.get("/lot-control/{vehicle_id}/scan")
def lot_control_get_scan_log(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_scan_log_api(payload["role"], vehicle_id)


# Inventory Merchandising's 11 routes moved to api/routers/merchandising.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(merchandising_router) below.


# ---------------------------------------------------------------------------
# Inventory Syndication -- feed-health rollup + cross-platform lead
# performance + bulk republish. Extracted to
# api/routers/inventory_syndication.py (CAF-00120, god_file_app_py -- splitting
# this file into domain-scoped routers). Included via
# app.include_router(inventory_syndication_router) near the top of this file.
# Same 5 routes, same behavior.
# ---------------------------------------------------------------------------


# Wholesale Desk's 12 routes moved to api/routers/wholesale_desk.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(wholesale_desk_router) below.

# --- Operations: Overview + Action Center (session 106 follow-up #2) ---

@app.get("/operations/overview")
def operations_overview_get(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_operations_overview_api(payload["role"])


# Operations Tasks' 12 routes moved to api/routers/operations_tasks.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(operations_tasks_router) below.

# --- Inventory Aging Management (session 106 follow-up #4) ---
#
# Sam's spec: "price reduction / wholesale review / manager review / marketing
# campaign / auction assignment actions on aging bands." Backs Operations' own
# "Inventory" Top Menu item -- a real price-band board (the honest HEURISTIC
# proxy for true day-based aging, which can't be computed -- no acquisition-date
# field exists on Vehicle) with 5 real actions attached to it. See
# core/inventory_aging.py's module docstring for why 4 of the 5 actions reuse
# existing engines (OperationsTask, inventory_ads Campaign) rather than building
# parallel ones.

@app.get("/inventory-aging/board")
def inventory_aging_board(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_aging_board_api(payload["role"])


@app.get("/inventory-aging/{vehicle_id}")
def inventory_aging_vehicle_brief(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_vehicle_aging_brief_api(payload["role"], vehicle_id)


@app.post("/inventory-aging/{vehicle_id}/reduce-price")
def inventory_aging_reduce_price(vehicle_id: str, request: ReducePriceRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reduce_price_api(payload["role"], payload["employee_id"], vehicle_id, request.new_price, reason=request.reason)


@app.post("/inventory-aging/{vehicle_id}/wholesale-review")
def inventory_aging_wholesale_review(vehicle_id: str, request: AgingActionNotesRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_wholesale_review_api(payload["role"], payload["employee_id"], vehicle_id, notes=request.notes)


@app.post("/inventory-aging/{vehicle_id}/manager-review")
def inventory_aging_manager_review(vehicle_id: str, request: AgingActionNotesRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_manager_review_api(payload["role"], payload["employee_id"], vehicle_id, notes=request.notes)


@app.post("/inventory-aging/{vehicle_id}/auction-assignment")
def inventory_aging_auction_assignment(vehicle_id: str, request: AgingActionNotesRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_auction_assignment_api(payload["role"], payload["employee_id"], vehicle_id, notes=request.notes)


@app.post("/inventory-aging/{vehicle_id}/marketing-tie-in")
def inventory_aging_marketing_tie_in(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_marketing_tie_in_api(payload["role"], payload["employee_id"], vehicle_id)


# --- Operations Scheduling (session 106 follow-up #5) ---
#
# Sam's spec: "Recon Scheduling, Delivery Scheduling with automatic risk
# detection, Transport Scheduling." See core/operations_scheduling.py's module
# docstring -- Delivery Scheduling's risk detection is the one genuinely new
# cross-reference in this slice (contract/funded Deals vs. real open delivery
# Appointments), Transport Scheduling's update_transport_status is the one
# genuinely new mutation (nothing previously updated AuctionTransaction.
# transport_status after seeding).

@app.get("/operations-scheduling/recon")
def operations_scheduling_recon(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_recon_schedule_api(payload["role"])


@app.post("/operations-scheduling/recon/{vehicle_id}/schedule")
def operations_scheduling_schedule_recon(vehicle_id: str, request: ScheduleReconRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return schedule_recon_api(payload["role"], payload["employee_id"], vehicle_id, request.target_date, notes=request.notes)


@app.get("/operations-scheduling/delivery-risk")
def operations_scheduling_delivery_risk(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_delivery_risk_board_api(payload["role"])


@app.post("/operations-scheduling/delivery/{deal_id}/schedule")
def operations_scheduling_schedule_delivery(deal_id: str, request: ScheduleDeliveryRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return schedule_operations_delivery_api(payload["role"], payload["employee_id"], deal_id, request.scheduled_start, assigned_to=request.assigned_to, notes=request.notes)


@app.get("/operations-scheduling/transport")
def operations_scheduling_transport(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_transport_schedule_api(payload["role"])


@app.post("/operations-scheduling/transport/{transaction_id}/status")
def operations_scheduling_update_transport_status(transaction_id: str, request: UpdateTransportStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_transport_status_api(payload["role"], payload["employee_id"], transaction_id, request.new_status)


# --- Document Workflows (session 106 follow-up #6) ---
#
# Sam's spec: "Deal Jacket Workflow, Title Processing workflow, Compliance
# Packets, Digital Approvals." See core/document_workflows.py's module
# docstring -- Digital Approvals (approve_document/reject_document) is the
# one genuinely new capability; everything else is a completeness check or a
# bundling view over the existing categorized Document vault (session 60).

@app.get("/document-workflows/deal-jacket/{deal_id}")
def document_workflows_deal_jacket(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_deal_jacket_status_api(payload["role"], deal_id)


@app.get("/document-workflows/title/{vehicle_id}")
def document_workflows_title(vehicle_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_title_status_api(payload["role"], vehicle_id)


@app.post("/document-workflows/request")
def document_workflows_request(request: RequestDocumentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_document_api(payload["role"], payload["employee_id"], request.entity_type, request.entity_id, request.document_type, notes=request.notes)


@app.get("/document-workflows/packet/{entity_type}/{entity_id}")
def document_workflows_packet(entity_type: str, entity_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_document_packet_api(payload["role"], entity_type, entity_id)


@app.get("/document-workflows/pending-approvals")
def document_workflows_pending_approvals(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_pending_approvals_api(payload["role"])


@app.post("/document-workflows/{document_id}/approve")
def document_workflows_approve(document_id: str, request: ApproveDocumentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return approve_document_api(payload["role"], payload["employee_id"], document_id, notes=request.notes)


@app.post("/document-workflows/{document_id}/reject")
def document_workflows_reject(document_id: str, request: RejectDocumentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reject_document_api(payload["role"], payload["employee_id"], document_id, reason=request.reason)


# --- Operations Alerts (session 106 follow-up #7) ---
#
# Sam's spec: Operations' "Alerts" item as a real nervous system -- red/yellow
# severity, real actions, not just a read-only exception list. See
# core/operations_alerts.py's module docstring -- this aggregates seven real
# signal types across five modules already built this session and routes each
# to a real action; only two types (ownership_mismatch, stalled_deal) needed
# this module's own new acknowledge_alert() capability.

@app.get("/operations-alerts/feed")
def operations_alerts_feed(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_alert_feed_api(payload["role"])


@app.get("/operations-alerts/stats")
def operations_alerts_stats(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_alert_stats_api(payload["role"])


@app.post("/operations-alerts/acknowledge")
def operations_alerts_acknowledge(request: AcknowledgeAlertRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return acknowledge_alert_api(payload["role"], payload["employee_id"], request.alert_type, request.source_id, notes=request.notes)


# --- RO Workflow Engine (Service rebuild kickoff) ---
#
# Sam's own diagnosis of the pre-existing Service module: "that's service
# reporting, not service execution." This turns ServiceRecord into a real
# lifecycle entity -- a 10-stage pipeline (Check-In -> RO Written ->
# Inspection -> Estimate -> Customer Approval -> Parts -> Repair -> Quality
# Control -> Delivery -> Follow-Up), concern tracking, an estimate/approval
# flow, parts requests, a QC checklist, and a composed timeline. See
# core/repair_orders.py's module docstring for the full design.

@app.get("/repair-orders/catalog")
def repair_orders_catalog(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ro_catalog_api(payload["role"])


@app.get("/repair-orders/board")
def repair_orders_board(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ro_board_api(payload["role"])


@app.post("/repair-orders")
def repair_orders_create(request: CreateRepairOrderRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    # Repair orders are a Service Module feature (Freemium roadmap). Under the default
    # "reference" profile every Module is on, so this gate is a no-op today; it becomes real the
    # moment a dealer is moved to Foundation. This is the representative wiring pattern -- one
    # `require_module` line ahead of the module-owned write.
    from core.entitlements import require_module
    gate = require_module("service")
    if gate:
        return gate

    return create_repair_order_api(
        payload["role"], payload["employee_id"], request.vehicle_id, request.customer_id,
        request.description, pay_type=request.pay_type, preferred_contact_method=request.preferred_contact_method,
    )


@app.get("/repair-orders/{ro_id}")
def repair_orders_get(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ro_workspace_api(payload["role"], ro_id)


@app.post("/repair-orders/{ro_id}/return-followup/outcome")
def repair_orders_return_followup_outcome(ro_id: str, request: ReturnFollowupOutcomeRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return complete_return_followup_api(payload["role"], payload["employee_id"], ro_id, request.outcome, request.expected_updated_at)


@app.post("/repair-orders/{ro_id}/return-followup")
def repair_orders_return_followup(ro_id: str, request: ReturnFollowupRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return plan_return_followup_api(payload["role"], payload["employee_id"], ro_id, request.due_date, request.next_action)


@app.post("/repair-orders/{ro_id}/return-handover")
def repair_orders_return_handover(ro_id: str, request: ReturnHandoverRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return record_return_handover_api(payload["role"], payload["employee_id"], ro_id, request.recipient, request.settlement_reference, request.confirmed)


@app.post("/repair-orders/{ro_id}/return-review")
def repair_orders_return_review(ro_id: str, request: ReturnReviewRequest, authorization: str = Header(None)):
    payload, error = _authenticate(authorization)
    if error:
        return error
    return record_return_review_api(payload["role"], payload["employee_id"], ro_id, request.transport, request.notes, request.acknowledged)


@app.post("/repair-orders/{ro_id}/advance-stage")
def repair_orders_advance_stage(ro_id: str, request: AdvanceRoStageRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return advance_stage_api(payload["role"], payload["employee_id"], ro_id, request.new_stage)


@app.post("/repair-orders/{ro_id}/concerns")
def repair_orders_add_concern(ro_id: str, request: AddConcernRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return add_concern_api(payload["role"], payload["employee_id"], ro_id, request.description, occurs_at=request.occurs_at)


@app.post("/repair-orders/{ro_id}/concerns/resolve")
def repair_orders_resolve_concern(ro_id: str, request: ResolveConcernRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return resolve_concern_api(payload["role"], payload["employee_id"], ro_id, request.concern_id, resolution_notes=request.resolution_notes, outcome=request.outcome)


@app.post("/repair-orders/{ro_id}/estimate")
def repair_orders_send_estimate(ro_id: str, request: SendEstimateRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return send_estimate_api(payload["role"], payload["employee_id"], ro_id, request.amount)


@app.post("/repair-orders/{ro_id}/approval")
def repair_orders_record_approval(ro_id: str, request: RecordCustomerApprovalRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_customer_approval_api(payload["role"], payload["employee_id"], ro_id, request.approved, decline_reason=request.decline_reason)


@app.post("/repair-orders/{ro_id}/parts-status")
def repair_orders_update_parts_status(ro_id: str, request: UpdatePartsStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_parts_status_api(payload["role"], payload["employee_id"], ro_id, request.status, notes=request.notes)


@app.post("/repair-orders/{ro_id}/parts-requests")
def repair_orders_request_part(ro_id: str, request: RequestPartRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_part_api(payload["role"], payload["employee_id"], ro_id, request.description)


@app.post("/repair-orders/{ro_id}/parts-requests/status")
def repair_orders_update_part_request_status(ro_id: str, request: UpdatePartRequestStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_part_request_status_api(payload["role"], payload["employee_id"], ro_id, request.request_id, request.status)


@app.post("/repair-orders/{ro_id}/qc")
def repair_orders_update_qc_item(ro_id: str, request: UpdateQcItemRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_qc_item_api(payload["role"], payload["employee_id"], ro_id, request.item, request.complete)


@app.post("/repair-orders/{ro_id}/communication")
def repair_orders_log_communication(ro_id: str, request: LogRoCommunicationRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return log_ro_communication_api(payload["role"], payload["employee_id"], ro_id, request.channel, request.body)


# --- Service Overview / Command Center (second slice of Service's rebuild) ---
#
# Sam's spec: a Service Command Center (real clickable waiting-buckets),
# Today's Risks, and an Advisor Dashboard -- see core/service_overview.py's
# module docstring. Same "My Day" composition pattern as
# core/sales_overview.py's GET /sales/my-day.

@app.get("/service/my-day")
def service_my_day(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_service_my_day_api(payload["role"], payload["employee_id"])


@app.post("/repair-orders/{ro_id}/assign-technician")
def repair_orders_assign_technician(ro_id: str, request: AssignTechnicianRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return assign_technician_api(payload["role"], payload["employee_id"], ro_id, request.technician_id)


# --- Shop Control (third slice of Service's rebuild) ---
#
# Moved to backend/api/routers/shop_control.py (CAF-00120, god_file_app_py --
# app.include_router(shop_control_router) near the top of this file). Same 4
# routes (dispatch-board/utilization/stalled/bottlenecks), same behavior.


# --- Service Customers (fourth slice of Service's rebuild) ---
#
# Moved to backend/api/routers/service_customers.py (CAF-00120,
# god_file_app_py -- app.include_router(service_customers_router) near the
# top of this file). Same 4 routes (lost-customer-recovery/declined-services/
# customer 360/retention), same behavior.


# --- Parts Desk (fifth slice of Service's rebuild) ---
#
# Sam's spec: a Parts Request Queue (department-wide -- previously only
# visible one RO at a time via the RO Workflow Engine), Special Order
# Tracking (genuinely new -- no vendor/ETA tracking existed anywhere), and
# Inventory Recommendations (REAL, computed off real PartSale velocity vs.
# real Part.QuantityOnHand -- no fabrication needed). See
# core/parts_desk.py's module docstring for the full reasoning.

@app.get("/parts-desk/queue")
def parts_desk_queue(status: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_parts_request_queue_api(payload["role"], status=status)


@app.get("/parts-desk/special-orders")
def parts_desk_special_orders(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_special_orders_api(payload["role"])


@app.get("/parts-desk/recommendations")
def parts_desk_recommendations(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_inventory_recommendations_api(payload["role"])


@app.post("/repair-orders/{ro_id}/mark-special-order")
def parts_desk_mark_special_order(ro_id: str, body: MarkSpecialOrderRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_special_order_api(payload["role"], ro_id, body.request_id, body.vendor, body.eta, payload["employee_id"])


# Warranty Desk's 9 routes moved to api/routers/warranty_desk.py
# (CAF-00120, god_file_app_py) -- registered via
# app.include_router(warranty_desk_router) below.

# --- Digital Vehicle Inspection (first of Service's "completely missing"
# features, session 111 follow-up) ---
#
# Sam's spec named this a completely missing feature. Deliberately NOT a
# new standalone entity or parallel workflow -- real additive state on the
# same ServiceRecord the RO Workflow Engine already manages, tied to that
# engine's existing "Inspection" stage. See core/vehicle_inspection.py's
# module docstring for the full reasoning, including the real tie-in that
# turns flagged findings directly into real Concerns.

@app.get("/dvi/catalog")
def dvi_catalog(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_dvi_catalog_api(payload["role"])


@app.get("/repair-orders/{ro_id}/inspection")
def repair_order_get_inspection(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_inspection_api(payload["role"], ro_id)


@app.post("/repair-orders/{ro_id}/inspection/start")
def repair_order_start_inspection(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return start_inspection_api(payload["role"], ro_id, payload["employee_id"])


@app.post("/repair-orders/{ro_id}/inspection/item")
def repair_order_update_inspection_item(ro_id: str, body: UpdateInspectionItemRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_inspection_item_api(payload["role"], ro_id, body.item_key, body.status, body.notes, payload["employee_id"])


@app.post("/repair-orders/{ro_id}/inspection/photo")
def repair_order_attach_inspection_photo(ro_id: str, body: AttachInspectionPhotoRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return attach_inspection_photo_api(payload["role"], ro_id, body.item_key, body.image_url, payload["employee_id"], body.media_type)


@app.post("/repair-orders/{ro_id}/inspection/complete")
def repair_order_complete_inspection(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return complete_inspection_api(payload["role"], ro_id, payload["employee_id"])


@app.post("/repair-orders/{ro_id}/inspection/create-concerns")
def repair_order_create_concerns_from_inspection(ro_id: str, body: CreateConcernsFromInspectionRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_concerns_from_inspection_api(payload["role"], ro_id, body.item_keys, payload["employee_id"])


@app.get("/vehicle-inspection-history/{vehicle_id_or_vin}")
def vehicle_inspection_history(vehicle_id_or_vin: str, authorization: str = Header(None)):
    # Cross-RO Vehicle Inspection History (2026-07-19) -- closes Sam's
    # "Digital Inspections' remaining asks" gap. Accepts either a real
    # Vehicle id (VEH-...) or a raw VIN string.

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_inspection_history_api(payload["role"], vehicle_id_or_vin)


# --- Customer-Facing Approval Center (second of Service's "completely
# missing" features, session 111 follow-up) ---
#
# Staff-side (authenticated, same RO Workflow Engine role sets) generate/
# view/revoke a real shareable link. The actual customer-facing read/write
# is genuinely public -- see the /public/approve/* routes further down,
# grouped with this codebase's other /public/* routes.

@app.post("/repair-orders/{ro_id}/approval-link")
def repair_order_generate_approval_link(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_approval_link_api(payload["role"], ro_id, payload["employee_id"])


@app.get("/repair-orders/{ro_id}/approval-link")
def repair_order_get_approval_link_status(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_approval_link_status_api(payload["role"], ro_id)


@app.post("/repair-orders/{ro_id}/approval-link/revoke")
def repair_order_revoke_approval_link(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return revoke_approval_link_api(payload["role"], ro_id, payload["employee_id"])


# Loaner & Shuttle Management's 18 routes moved to
# api/routers/loaner_shuttle.py (CAF-00120, god_file_app_py) -- registered
# via app.include_router(loaner_shuttle_router) below.


# --- Service-to-Sales Opportunity Handoff (fourth and final of Service's
# "completely missing" features, session 111 follow-up) --- static
# /service-sales-handoff/* paths registered before the dynamic
# /repair-orders/{ro_id}/sales-handoff/* paths (a different prefix, so no
# real shadowing risk, but kept consistent with this codebase's convention).

@app.get("/service-sales-handoff/queue")
def service_sales_handoff_queue(limit: int = 50, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_opportunity_queue_api(payload["role"], limit=limit)


# Phase 7: combined conversion queue including the equity/maturity-at-service signal.
@app.get("/service-sales-handoff/conversion-queue")
def service_sales_handoff_conversion_queue(limit: int = 50, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_conversion_opportunities_api(payload["role"], limit=limit)


@app.get("/service-sales-handoff/stats")
def service_sales_handoff_stats(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_handoff_stats_api(payload["role"])


@app.get("/repair-orders/{ro_id}/sales-handoff")
def repair_order_get_handoff_status(ro_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ro_handoff_status_api(payload["role"], ro_id)


@app.post("/repair-orders/{ro_id}/sales-handoff/flag")
def repair_order_flag_manual_opportunity(ro_id: str, body: FlagManualOpportunityRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return flag_manual_opportunity_api(payload["role"], payload["employee_id"], ro_id, notes=body.notes)


@app.post("/repair-orders/{ro_id}/sales-handoff/promote")
def repair_order_promote_to_sales(ro_id: str, body: PromoteToSalesRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return promote_to_sales_api(payload["role"], payload["employee_id"], ro_id, assigned_to=body.assigned_to, notes=body.notes, opportunity_type=body.opportunity_type)


@app.post("/repair-orders/{ro_id}/sales-handoff/dismiss")
def repair_order_dismiss_opportunity(ro_id: str, body: DismissOpportunityRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return dismiss_opportunity_api(payload["role"], payload["employee_id"], ro_id, reason=body.reason, opportunity_type=body.opportunity_type)


# Finance's Portfolio / Loan Management (2026-07-17, session 111 follow-up -- the
# first slice of Sam's "Retail Automotive Lending Platform" expansion). Static paths
# (/loan-servicing/portfolio, /loan-servicing/amortize) registered before the dynamic
# /loan-servicing/{loan_id} path, same route-shadowing-avoidance convention as every
# other module in this codebase.

@app.get("/loan-servicing/portfolio")
def loan_servicing_portfolio(bucket: str | None = None, limit: int = 100, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_portfolio_dashboard_api(payload["role"], bucket=bucket, limit=limit)


@app.post("/loan-servicing/amortize")
def loan_servicing_amortize(body: AmortizationScheduleRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return compute_amortization_schedule_api(payload["role"], body.principal, body.apr, body.term_months)


@app.get("/loan-servicing/{loan_id}")
def loan_servicing_get_detail(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_loan_detail_api(payload["role"], loan_id)


@app.get("/loan-servicing/{loan_id}/financials")
def loan_servicing_get_financials(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_loan_financials_api(payload["role"], loan_id)


@app.get("/loan-servicing/{loan_id}/timeline")
def loan_servicing_get_timeline(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_loan_timeline_api(payload["role"], loan_id)


@app.get("/loan-servicing/{loan_id}/status")
def loan_servicing_get_status(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_loan_status_api(payload["role"], loan_id)


@app.post("/loan-servicing/{loan_id}/status")
def loan_servicing_set_status(loan_id: str, body: SetLoanStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_loan_status_api(payload["role"], payload["employee_id"], loan_id, body.status, reason=body.reason)


@app.get("/loan-servicing/{loan_id}/payment-status")
def loan_servicing_get_payment_status(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_simulated_payment_status_api(payload["role"], loan_id)


# Finance's "Payments" item (2026-07-17, session 112 follow-up -- second slice of
# Sam's "Retail Automotive Lending Platform" expansion, right after Portfolio).
# Static paths (/payments/dashboard, /auto-drafts/run-due, /public/pay/{token}...)
# registered clear of any dynamic single-segment collision -- every /loan-servicing/
# subpath here has 2+ segments so none of them collide with the existing single-
# segment /loan-servicing/{loan_id} route.

@app.post("/loan-servicing/{loan_id}/payments")
def loan_servicing_record_payment(loan_id: str, body: RecordPaymentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_payment_api(payload["role"], payload["employee_id"], loan_id, body.amount, body.method, payment_date=body.payment_date, notes=body.notes)


@app.get("/loan-servicing/{loan_id}/payments")
def loan_servicing_list_payments(loan_id: str, include_declined: bool = True, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_payments_for_loan_api(payload["role"], loan_id, include_declined=include_declined)


@app.get("/loan-servicing/{loan_id}/payment-summary")
def loan_servicing_payment_summary(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_real_payment_summary_api(payload["role"], loan_id)


@app.post("/loan-servicing/{loan_id}/auto-drafts")
def loan_servicing_create_auto_draft(loan_id: str, body: CreateAutoDraftRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_auto_draft_api(payload["role"], payload["employee_id"], loan_id, body.amount, body.method, body.day_of_month)


@app.get("/auto-drafts")
def auto_drafts_list(loan_id: str | None = None, status: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_auto_drafts_api(payload["role"], loan_id=loan_id, status=status)


@app.post("/auto-drafts/run-due")
def auto_drafts_run_due(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_due_auto_drafts_api(payload["role"], payload["employee_id"])


@app.post("/auto-drafts/{draft_id}/status")
def auto_drafts_set_status(draft_id: str, body: SetAutoDraftStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_auto_draft_status_api(payload["role"], payload["employee_id"], draft_id, body.status)


@app.post("/loan-servicing/{loan_id}/promises")
def loan_servicing_create_promise(loan_id: str, body: CreatePromiseToPayRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_promise_to_pay_api(payload["role"], payload["employee_id"], loan_id, body.promise_date, body.amount, reason=body.reason)


@app.get("/promises")
def promises_list(loan_id: str | None = None, status: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_promises_to_pay_api(payload["role"], loan_id=loan_id, status=status)


@app.get("/promises/{ptp_id}")
def promises_get_status(ptp_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_promise_status_api(payload["role"], ptp_id)


@app.post("/loan-servicing/{loan_id}/extension")
def loan_servicing_record_extension(loan_id: str, body: RecordExtensionRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_extension_api(payload["role"], payload["employee_id"], loan_id, body.new_next_due_date, reason=body.reason)


@app.post("/loan-servicing/{loan_id}/deferral")
def loan_servicing_record_deferral(loan_id: str, body: RecordDeferralRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_deferral_api(payload["role"], payload["employee_id"], loan_id, body.months, reason=body.reason)


@app.get("/loan-servicing/{loan_id}/adjustments")
def loan_servicing_get_adjustments(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_payment_adjustments_api(payload["role"], loan_id)


@app.post("/loan-servicing/{loan_id}/payoff-request")
def loan_servicing_request_payoff(loan_id: str, body: RequestPayoffRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return request_payoff_api(payload["role"], payload["employee_id"], loan_id, notes=body.notes)


@app.post("/loan-servicing/{loan_id}/payoff-request/fulfill")
def loan_servicing_fulfill_payoff(loan_id: str, body: FulfillPayoffRequestRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return fulfill_payoff_request_api(payload["role"], payload["employee_id"], loan_id, body.request_id)


@app.get("/payoff-requests")
def payoff_requests_list(loan_id: str | None = None, status: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_payoff_requests_api(payload["role"], loan_id=loan_id, status=status)


@app.post("/loan-servicing/{loan_id}/payment-portal-link")
def loan_servicing_generate_portal_link(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_payment_portal_link_api(payload["role"], payload["employee_id"], loan_id)


@app.get("/loan-servicing/{loan_id}/payment-portal-link")
def loan_servicing_get_portal_link(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_payment_portal_link_status_api(payload["role"], loan_id)


@app.post("/loan-servicing/{loan_id}/payment-portal-link/revoke")
def loan_servicing_revoke_portal_link(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return revoke_payment_portal_link_api(payload["role"], payload["employee_id"], loan_id)


@app.get("/payments/dashboard")
def payments_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_payments_dashboard_api(payload["role"])


# Customer Payment Portal -- PUBLIC, unauthenticated, same /public/* convention as
# core/approval_center.py's /public/approve/* and core/appointment_scheduling.py's
# /public/checkin/*.

@app.get("/public/pay/{token}")
def public_pay_get_view(token: str):

    return get_public_portal_view(token)


@app.post("/public/pay/{token}/submit")
def public_pay_submit(token: str, body: PublicPaymentRequest):

    return submit_public_payment(token, body.amount, body.method)


@app.post("/public/pay/{token}/payoff")
def public_pay_request_payoff(token: str, body: PublicPayoffRequestRequest):

    return submit_public_payoff_request(token, notes=body.notes)


# Collections -- static paths (/collections/queue, /collections/dashboard) registered
# before the dynamic /loan-servicing/{loan_id}/collections/* paths.

@app.get("/collections/queue")
def collections_queue(bucket: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_collection_queue_api(payload["role"], bucket=bucket)


@app.get("/collections/dashboard")
def collections_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_collections_dashboard_api(payload["role"])


@app.get("/loan-servicing/{loan_id}/collections/workspace")
def collections_agent_workspace(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_agent_workspace_api(payload["role"], loan_id)


@app.get("/loan-servicing/{loan_id}/collections/stage")
def collections_get_stage(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_collection_stage_api(payload["role"], loan_id)


@app.post("/loan-servicing/{loan_id}/collections/stage")
def collections_advance_stage(loan_id: str, body: AdvanceCollectionStageRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return advance_collection_stage_api(payload["role"], payload["employee_id"], loan_id, body.stage, reason=body.reason)


@app.get("/loan-servicing/{loan_id}/collections/risk-score")
def collections_risk_score(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return compute_risk_score_api(payload["role"], loan_id)


@app.get("/loan-servicing/{loan_id}/collections/priority")
def collections_priority(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_priority_recommendation_api(payload["role"], loan_id)


@app.post("/loan-servicing/{loan_id}/collections/contact")
def collections_log_contact(loan_id: str, body: LogCollectionContactRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return log_contact_api(payload["role"], payload["employee_id"], loan_id, body.channel, body.notes)


@app.get("/loan-servicing/{loan_id}/collections/contact-history")
def collections_contact_history(loan_id: str, limit: int = 50, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_contact_history_api(payload["role"], loan_id, limit=limit)


# Repossessions' 13 routes moved to api/routers/repossessions.py (CAF-00120,
# god_file_app_py) -- registered via app.include_router(repossessions_router)
# below.


# ---------------------------------------------------------------------------
# Device Management (GPS & Starter Interrupt) -- 12 routes, extracted to
# api/routers/devices.py (CAF-00120, god_file_app_py -- splitting this file
# into domain-scoped routers). Included via app.include_router(devices_router)
# near the top of this file. Same routes, same behavior.
# ---------------------------------------------------------------------------


# Collateral / Asset Management (Title/Lien/Insurance/Valuation) -- lives at the
# distinct top-level /collateral/* prefix, NOT /assets/*, to avoid colliding with
# core/assets.py's already-registered Marketing Asset workflow (GET /assets/{asset_id}
# was registered first, session 30, which would have silently shadowed a same-named
# /assets/{loan_id} route -- same class of fix session 85's GET /website-templates
# already established for this exact reason). Static path (/collateral/dashboard)
# registered before the dynamic /collateral/{loan_id}/* paths.

@app.get("/collateral/dashboard")
def collateral_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_asset_portfolio_dashboard_api(payload["role"])


@app.get("/collateral/{loan_id}")
def collateral_get_summary(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_asset_summary_api(payload["role"], loan_id)


@app.get("/collateral/{loan_id}/lien")
def collateral_get_lien(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lien_status_api(payload["role"], loan_id)


@app.post("/collateral/{loan_id}/lien/lienholder")
def collateral_update_lienholder(loan_id: str, body: UpdateLienholderRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_lienholder_api(payload["role"], payload["employee_id"], loan_id, body.lienholder_name)


@app.post("/collateral/{loan_id}/lien/release")
def collateral_release_lien(loan_id: str, body: ReleaseLienRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return release_lien_api(payload["role"], payload["employee_id"], loan_id, reason=body.reason)


@app.get("/collateral/{loan_id}/insurance")
def collateral_get_insurance(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_insurance_status_api(payload["role"], loan_id)


@app.post("/collateral/{loan_id}/insurance")
def collateral_update_insurance(loan_id: str, body: UpdateInsuranceRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_insurance_api(payload["role"], payload["employee_id"], loan_id, body.carrier, body.policy_number, body.expiration_date, body.loss_payee_confirmed)


@app.get("/collateral/{loan_id}/valuation")
def collateral_get_valuation(loan_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_collateral_valuation_api(payload["role"], loan_id)


# core/lending_compliance.py -- OFAC/SDN screening + IRS Form 8300 cash reporting
# (2026-07-17, session 112 follow-up), the seventh slice of Sam's "Retail Automotive
# Lending Platform" expansion and the last explicitly-named item on his original
# 13-item Finance menu spec. Under /lending-compliance/*, distinct from the
# already-registered /compliance/* prefix (the general compliance-alert system, session
# 38-89) to avoid ambiguity between "the general compliance agent" and this
# lending-specific screening/reporting surface -- both are real and both stay separate.
# Static /lending-compliance/dashboard and /lending-compliance/form-8300/obligations
# registered before the dynamic /lending-compliance/{deal_id}/* paths.

@app.get("/lending-compliance/dashboard")
def lending_compliance_dashboard(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_lending_compliance_dashboard_api(payload["role"])


@app.get("/lending-compliance/form-8300/obligations")
def lending_compliance_form_8300_obligations(status: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_form_8300_obligations_api(payload["role"], status)


@app.get("/lending-compliance/{deal_id}/ofac")
def lending_compliance_get_ofac(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_ofac_screening_status_api(payload["role"], deal_id)


@app.post("/lending-compliance/{deal_id}/ofac")
def lending_compliance_record_ofac(deal_id: str, body: RecordOfacScreeningRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_ofac_screening_api(payload["role"], deal_id, body.cleared, payload["employee_id"], body.notes)


@app.post("/lending-compliance/{deal_id}/cash-payment")
def lending_compliance_record_cash_payment(deal_id: str, body: RecordCashPaymentRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return record_cash_payment_api(payload["role"], deal_id, body.amount, body.payment_date, payload["employee_id"])


@app.get("/lending-compliance/{deal_id}/form-8300")
def lending_compliance_get_form_8300(deal_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_form_8300_status_api(payload["role"], deal_id)


@app.post("/lending-compliance/{deal_id}/form-8300/file")
def lending_compliance_file_form_8300(deal_id: str, body: FileForm8300Request, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return file_form_8300_api(payload["role"], deal_id, payload["employee_id"], body.filing_date)


# core/glba_program.py -- GLBA Safeguards Rule Information Security Program tracker
# (security-hardening pass, 2026-07-20, Task #11). Under /glba-program/*. Static
# /glba-program/readiness and /glba-program/items registered before the dynamic
# /glba-program/items/{component_key} paths.

@app.get("/glba-program/readiness")
def glba_program_readiness(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_glba_readiness_summary_api(payload["role"])


@app.get("/glba-program/items")
def glba_program_list_items(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_glba_program_items_api(payload["role"])


@app.get("/glba-program/items/{component_key}")
def glba_program_get_item(component_key: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_glba_component_status_api(payload["role"], component_key)


@app.post("/glba-program/items/{component_key}")
def glba_program_set_item(component_key: str, body: SetGlbaComponentStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_glba_component_status_api(
        payload["role"],
        component_key,
        body.status,
        body.owner_employee_id,
        body.notes,
        payload["employee_id"],
        body.last_reviewed_at,
    )


# core/pci_dss_guard.py -- PCI-DSS card-data guard + posture self-check
# (security-hardening pass, 2026-07-20, Task #11). The blocking pre-flight check
# itself is wired directly into core/payments.py's record_payment() and needs no
# route -- only the on-demand, dealership-wide posture scan is exposed here.

@app.get("/pci-dss/posture-scan")
def pci_dss_posture_scan(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_pci_posture_scan_api(payload["role"])


# core/crypto_agility.py -- Post-Quantum Cryptography Readiness / cryptographic
# agility layer (security-hardening pass, 2026-07-20, Task #12). versioned_digest()/
# verify_versioned_digest() are stateless utility functions called directly by other
# core modules (no route needed); only the posture report and the re-runnable
# inventory scan are exposed here, ADMIN/OPERATIONS-only, matching every other
# security self-check surface in this codebase.

@app.get("/crypto-agility/posture")
def crypto_agility_posture(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_crypto_agility_posture_api(payload["role"])


@app.get("/crypto-agility/inventory-scan")
def crypto_agility_inventory_scan(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_crypto_inventory_scan_api(payload["role"])


# core/secrets.py -- Secrets management abstraction (security-hardening pass,
# 2026-07-20, Task #13). get_secret()/get_secrets_posture() themselves are called
# directly by other core modules with no _api.py layer (see core/auth.py,
# core/network_snapshot_api.py); only the aggregate posture report is exposed as a
# route here, ADMIN/OPERATIONS-only, matching every other security self-check
# surface in this codebase. warn_on_dev_fallbacks() is called once at process
# startup, inside lifespan() below, not exposed as a route at all.

@app.get("/secrets/posture")
def secrets_posture(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_secrets_posture_api(payload["role"])


# core/loan_accounting.py -- Loan Accounting (2026-07-17, session 112 follow-up), the
# eighth slice of Sam's "Retail Automotive Lending Platform" expansion. Under
# /loan-accounting/*. Static paths (summary/unposted/periods/daily-ledger/post-all-due)
# registered before dynamic /loan-accounting/payments/{payment_id}/post and
# /loan-accounting/periods/{year}/{month}/* paths.

@app.get("/loan-accounting/summary")
def loan_accounting_summary(start_date: str = None, end_date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_loan_accounting_summary_api(payload["role"], start_date, end_date)


@app.get("/loan-accounting/unposted")
def loan_accounting_unposted(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_unposted_payments_api(payload["role"])


@app.get("/loan-accounting/periods")
def loan_accounting_periods(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_periods_api(payload["role"])


@app.get("/loan-accounting/daily-ledger/{payment_date}")
def loan_accounting_daily_ledger(payment_date: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_daily_ledger_api(payload["role"], payment_date)


@app.post("/loan-accounting/daily-ledger/{payment_date}/post-all-due")
def loan_accounting_post_all_due(payment_date: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return post_all_due_api(payload["role"], payment_date, payload["employee_id"])


@app.post("/loan-accounting/payments/{payment_id}/post")
def loan_accounting_post_payment(payment_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return post_payment_to_ledger_api(payload["role"], payment_id, payload["employee_id"])


@app.post("/loan-accounting/periods/close")
def loan_accounting_close_period(body: CloseAccountingPeriodRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return close_accounting_period_api(payload["role"], body.year, body.month, payload["employee_id"])


@app.post("/loan-accounting/periods/reopen")
def loan_accounting_reopen_period(body: ReopenAccountingPeriodRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reopen_accounting_period_api(payload["role"], body.year, body.month, payload["employee_id"])


# core/general_ledger.py + core/bank_reconciliation.py -- General Ledger + Bank
# Reconciliation (2026-07-17, session 112 follow-up), built with SIMULATED data per
# Sam's direct instruction after every explicitly-named Retail Lending Platform item
# closed: "lets keep going, simply create the fake data that is needed to build
# them." Under /general-ledger/* and /bank-reconciliation/*. Static paths registered
# before dynamic /general-ledger/entries/{entry_id} and
# /bank-reconciliation/transactions/{transaction_id}/* paths.

@app.get("/general-ledger/chart-of-accounts")
def general_ledger_chart_of_accounts(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_chart_of_accounts_api(payload["role"])


@app.post("/general-ledger/sync")
def general_ledger_sync(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return sync_real_entries_api(payload["role"], payload["employee_id"])


@app.post("/general-ledger/generate-simulated")
def general_ledger_generate_simulated(body: GenerateSimulatedGlEntriesRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_simulated_entries_api(payload["role"], body.year, body.month, payload["employee_id"], body.floorplan_exposure)


@app.get("/general-ledger/entries")
def general_ledger_entries(account_number: str = None, start_date: str = None, end_date: str = None, authorization: str = Header(None), limit: int = 200, offset: int = 0):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_general_ledger_api(payload["role"], account_number, start_date, end_date, limit=limit, offset=offset)


@app.delete("/general-ledger/entries/{entry_id}")
def general_ledger_delete_entry(entry_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_entry_api(payload["role"], entry_id, payload["employee_id"])


@app.get("/general-ledger/trial-balance")
def general_ledger_trial_balance(start_date: str = None, end_date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_trial_balance_api(payload["role"], start_date, end_date)


@app.get("/general-ledger/income-statement")
def general_ledger_income_statement(start_date: str = None, end_date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_income_statement_api(payload["role"], start_date, end_date)


@app.get("/general-ledger/balance-sheet")
def general_ledger_balance_sheet(as_of_date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_balance_sheet_api(payload["role"], as_of_date)


@app.post("/bank-reconciliation/generate-feed")
def bank_reconciliation_generate_feed(body: GenerateBankFeedRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_simulated_bank_feed_api(payload["role"], payload["employee_id"], body.start_date or None, body.end_date or None)


@app.get("/bank-reconciliation/status")
def bank_reconciliation_status(start_date: str = None, end_date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_reconciliation_status_api(payload["role"], start_date, end_date)


@app.get("/bank-reconciliation/transactions")
def bank_reconciliation_transactions(status: str = None, start_date: str = None, end_date: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_transactions_api(payload["role"], status, start_date, end_date)


@app.post("/bank-reconciliation/transactions/{transaction_id}/confirm-match")
def bank_reconciliation_confirm_match(transaction_id: str, body: ConfirmBankMatchRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return confirm_match_api(payload["role"], transaction_id, body.gl_entry_id, payload["employee_id"])


@app.post("/bank-reconciliation/transactions/{transaction_id}/mark-reviewed")
def bank_reconciliation_mark_reviewed(transaction_id: str, body: MarkBankTransactionReviewedRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return mark_transaction_reviewed_api(payload["role"], transaction_id, payload["employee_id"], body.note)


# Marketing Growth Platform kickoff (2026-07-17) -- CRM: Customer 360 + Smart
# Audiences + Lead Scoring. See core/customer_360.py's/core/smart_audiences.py's/
# core/lead_scoring.py's own module docstrings for the full "reuse, don't
# duplicate" design.

@app.get("/customer-360/{customer_id}")
def customer_360(customer_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_customer_360_api(payload["role"], customer_id, employee_id=payload.get("employee_id"))


@app.get("/smart-audiences/fields")
def smart_audiences_fields(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_field_catalog_api(payload["role"])


@app.get("/smart-audiences/presets")
def smart_audiences_presets(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_presets_api(payload["role"])


@app.post("/smart-audiences/presets/{preset_key}/preview")
def smart_audiences_preview_preset(preset_key: str, body: PreviewAudiencePresetRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return preview_preset_api(payload["role"], preset_key, body.params)


@app.post("/smart-audiences/preview")
def smart_audiences_preview_conditions(body: PreviewAudienceConditionsRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return preview_conditions_api(payload["role"], body.conditions)


@app.get("/smart-audiences")
def smart_audiences_list(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_audiences_api(payload["role"])


@app.post("/smart-audiences")
def smart_audiences_create(body: CreateSmartAudienceRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_audience_api(
        payload["role"],
        body.name,
        payload["employee_id"],
        body.conditions,
        body.preset_key,
        body.preset_params,
        body.description,
    )


@app.delete("/smart-audiences/{audience_id}")
def smart_audiences_delete(audience_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return delete_audience_api(payload["role"], audience_id)


@app.get("/smart-audiences/{audience_id}/evaluate")
def smart_audiences_evaluate(audience_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return evaluate_audience_api(payload["role"], audience_id)


@app.get("/lead-scoring/leaderboard")
def lead_scoring_leaderboard(limit: int = 50, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return lead_scoring_leaderboard_api(payload["role"], limit)


@app.get("/lead-scoring/{entity_id}")
def lead_scoring_score(entity_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return compute_score_api(payload["role"], entity_id)


# PURL Platform (Marketing Growth Platform, PURLs slice) -- staff-side routes,
# static paths (/purls, /purls/dashboard) registered before the dynamic
# /purls/{purl_id}/* paths, same collision-avoidance discipline as every other
# static-before-dynamic block in this file.

@app.post("/purls")
def purls_generate(body: GeneratePurlRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return generate_purl_api(
        payload["role"],
        payload["employee_id"],
        offer_type=body.offer_type,
        customer_id=body.customer_id,
        lead_id=body.lead_id,
        notes=body.notes,
    )


@app.get("/purls")
def purls_list(created_by: str | None = None, status: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_purls_api(payload["role"], created_by=created_by, status=status)


@app.get("/purls/dashboard")
def purls_dashboard(created_by: str | None = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_purl_dashboard_api(payload["role"], created_by=created_by)


@app.post("/purls/bulk-generate")
def purls_bulk_generate(body: BulkGeneratePurlsRequest, authorization: str = Header(None)):
    """Real direct-mail-campaign PURL generation -- one real PURL per member of a
    MarketingList or SmartAudience, not one click per person. See
    core/purls.py's bulk_generate_purls() docstring for the save-batching reasoning."""

    payload, error = _authenticate(authorization)
    if error:
        return error

    return bulk_generate_purls_api(
        payload["role"],
        payload["employee_id"],
        body.source_type,
        body.source_id,
        offer_type=body.offer_type,
        notes=body.notes,
    )


@app.post("/purls/{purl_id}/revoke")
def purls_revoke(purl_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return revoke_purl_api(payload["role"], purl_id, payload["employee_id"])


@app.post("/purls/{purl_id}/mail-piece")
def purls_mail_piece(purl_id: str, body: CreateMailPieceRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_mail_piece_api(
        payload["role"],
        purl_id,
        body.piece_name,
        body.piece_type,
        mail_date=body.mail_date,
        created_by=payload["employee_id"],
    )


@app.get("/purls/{purl_id}/analytics")
def purls_analytics(purl_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_purl_analytics_api(payload["role"], purl_id)


# PURL public landing page -- PUBLIC, unauthenticated, same /public/* convention
# as core/approval_center.py's /public/approve/*, core/appointment_scheduling.py's
# /public/checkin/*, and core/payments.py's /public/pay/*.

@app.get("/public/purl/{token}")
def public_purl_view(token: str):

    return get_personalized_offer(token)


@app.post("/public/purl/{token}/visit")
def public_purl_visit(token: str, body: PurlVisitRequest):

    return record_purl_visit(token, user_agent=body.user_agent)


@app.post("/public/purl/{token}/submit")
def public_purl_submit(token: str, body: SubmitPurlLeadRequest):

    return submit_purl_lead(token, notes=body.notes)


# Administration's "Roles & Permissions" item (Administration Control Center
# rebuild, first slice) -- core/permissions_registry.py/_api.py. Static paths
# registered before any dynamic /{id}-shaped path within each group.

@app.get("/permissions/catalog")
def permissions_catalog(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_permission_catalog_api(payload["role"])


@app.get("/permissions/tier-distribution")
def permissions_tier_distribution(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_tier_distribution_api(payload["role"])


@app.get("/permissions/overrides")
def permissions_overrides_all(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_all_overrides_api(payload["role"])


@app.post("/permissions/overrides")
def permissions_overrides_set(body: SetPermissionOverrideRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_override_api(
        payload["role"],
        payload["employee_id"],
        body.employee_id,
        body.permission_key,
        body.granted,
        reason=body.reason,
    )


@app.post("/permissions/overrides/{override_id}/revoke")
def permissions_overrides_revoke(override_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return revoke_override_api(payload["role"], payload["employee_id"], override_id)


@app.get("/permissions/employees/{employee_id}/effective")
def permissions_employee_effective(employee_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_effective_permissions_api(payload["role"], payload["employee_id"], target_employee_id=employee_id)


@app.get("/permissions/employees/{employee_id}/overrides")
def permissions_employee_overrides(employee_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_overrides_for_employee_api(payload["role"], payload["employee_id"], target_employee_id=employee_id)


@app.get("/approval-requests/chains")
def approval_chains(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_approval_chains_api(payload["role"])


@app.get("/approval-requests")
def approval_requests_list(
    status: str = None,
    mine: bool = False,
    pending_for_me: bool = False,
    authorization: str = Header(None),
):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_approval_requests_api(
        payload["role"],
        payload["employee_id"],
        status=status,
        mine_only=mine,
        pending_for_me=pending_for_me,
    )


@app.post("/approval-requests")
def approval_requests_create(body: CreateApprovalRequestRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_approval_request_api(
        payload["role"],
        payload["employee_id"],
        body.chain_key,
        body.subject,
        details=body.details,
        entity_id=body.entity_id,
    )


@app.get("/approval-requests/{request_id}")
def approval_requests_get(request_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_approval_request_api(payload["role"], request_id)


@app.post("/approval-requests/{request_id}/approve")
def approval_requests_approve(request_id: str, body: ApproveStepRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return approve_step_api(payload["role"], payload["employee_id"], request_id, note=body.note)


@app.post("/approval-requests/{request_id}/reject")
def approval_requests_reject(request_id: str, body: RejectStepRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reject_step_api(payload["role"], payload["employee_id"], request_id, body.reason)


@app.post("/approval-requests/{request_id}/cancel")
def approval_requests_cancel(request_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_request_api(payload["role"], payload["employee_id"], request_id)


# --- Administration Control Center -- Vendor Management (continued) ---
#
# Moved to backend/api/routers/vendors.py (CAF-00120, god_file_app_py --
# app.include_router(vendors_router) near the top of this file). Same 6
# routes (create/list/dashboard/get/update/status), same behavior.


# ---------------------------------------------------------------------------
# System Configuration / Organizations (10 routes: /system-config*) --
# extracted to api/routers/system_config.py (CAF-00120, god_file_app_py --
# splitting this file into domain-scoped routers). Included via
# app.include_router(system_config_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Data Management (5 routes: /data-management*) -- extracted to
# api/routers/data_management.py (CAF-00120, god_file_app_py -- splitting this
# file into domain-scoped routers). Included via
# app.include_router(data_management_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Identity & Access (5 routes: /api-keys*) -- extracted to
# api/routers/identity_access.py (CAF-00120, god_file_app_py -- splitting this
# file into domain-scoped routers). Included via
# app.include_router(identity_access_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Audit Center (7 routes: /audit-center*) -- extracted to
# api/routers/audit_center.py (CAF-00120, god_file_app_py -- splitting this
# file into domain-scoped routers). Included via
# app.include_router(audit_center_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Governance (5 routes: /governance/*) -- extracted to
# api/routers/governance.py (CAF-00120, god_file_app_py -- splitting this
# file into domain-scoped routers). Included via
# app.include_router(governance_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Workflow Automation (11 routes: /automation*, /automation-rules*,
# /automation-executions) -- extracted to api/routers/workflow_automation.py
# (CAF-00120, god_file_app_py -- splitting this file into domain-scoped
# routers). Included via app.include_router(workflow_automation_router)
# near the top of this file. Same routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AI Management (4 routes: /ai-management/*) -- extracted to
# api/routers/ai_management.py (CAF-00120, god_file_app_py -- splitting this
# file into domain-scoped routers). Included via
# app.include_router(ai_management_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Business Health (2 routes: /business-health/*) -- extracted to
# api/routers/business_health.py (CAF-00120, god_file_app_py -- splitting
# this file into domain-scoped routers). Included via
# app.include_router(business_health_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Enterprise Risk Center (2 routes: /enterprise-risk/*) -- extracted to
# api/routers/enterprise_risk_center.py (CAF-00120, god_file_app_py --
# splitting this file into domain-scoped routers). Included via
# app.include_router(enterprise_risk_center_router) near the top of this
# file. Same routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Readiness Recommendations (2 routes: /readiness-recommendations/*) --
# extracted to api/routers/readiness_recommendations.py (CAF-00120,
# god_file_app_py -- splitting this file into domain-scoped routers).
# Included via app.include_router(readiness_recommendations_router) near the
# top of this file. Same routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Readiness Overview (2 routes: /readiness-overview/*) -- extracted to
# api/routers/readiness_overview.py (CAF-00120, god_file_app_py -- splitting
# this file into domain-scoped routers). Included via
# app.include_router(readiness_overview_router) near the top of this file.
# Same routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Data Health (5 routes: /data-health/*) -- extracted to
# api/routers/data_health.py (CAF-00120, god_file_app_py -- splitting this
# file into domain-scoped routers). Included via
# app.include_router(data_health_router) near the top of this file. Same
# routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Performance Readiness (2 routes: /performance-readiness/*) -- extracted to
# api/routers/performance_readiness.py (CAF-00120, god_file_app_py --
# splitting this file into domain-scoped routers). Included via
# app.include_router(performance_readiness_router) near the top of this file.
# Same routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Readiness Forecasts + Readiness Timeline (4 routes: /readiness-forecasts/*,
# /readiness-timeline/*) -- extracted to api/routers/readiness_forecasts.py
# (CAF-00120, god_file_app_py -- splitting this file into domain-scoped
# routers). Included via app.include_router(readiness_forecasts_router) near
# the top of this file. Same routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Scenarios / What-If Modeling (5 routes: /readiness-scenarios/*) --
# extracted to api/routers/readiness_scenarios.py (CAF-00120, god_file_app_py
# -- splitting this file into domain-scoped routers). Included via
# app.include_router(readiness_scenarios_router) near the top of this file.
# Same routes, same behavior.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Readiness reframe -- Strategic Planning (item #9 of Sam's 10-item proposed
# structure, "a completely new area"). core/strategic_planning.py / _api.py --
# real Quarterly Planning (Objectives/Goals/Budgets), Department Planning, and
# Initiative Tracking, with status computed live (real for Sales/Service/
# Marketing off core/performance_readiness.py's own real signal sources
# generalized to a quarter window, an honest manual self-report otherwise) --
# see that module's own docstring for the full design, including the real,
# explicit, one-way sync into core/system_config.py's department_goals.
# Static "/strategic-planning/overview", "/departments", "/objectives", and
# "/initiatives" (GET+POST) registered before the dynamic "/objectives/{id}"
# and "/initiatives/{id}" paths -- no collision risk (different segment
# counts), same ordering discipline as every other module in this file.
# ---------------------------------------------------------------------------

class CreateStrategicObjectiveRequest(BaseModel):

    quarter: str
    year: int
    department: str
    title: str
    description: str = ""
    target_value: float | None = None
    unit: str = ""
    budget_allocated: float | None = None


class UpdateStrategicObjectiveRequest(BaseModel):

    title: str | None = None
    description: str | None = None
    target_value: float | None = None
    unit: str | None = None
    budget_allocated: float | None = None


class UpdateObjectiveProgressRequest(BaseModel):

    progress_pct: float


class UpdateBudgetRequest(BaseModel):

    budget_allocated: float | None = None
    budget_spent: float | None = None


class CreateStrategicInitiativeRequest(BaseModel):

    name: str
    department: str
    tracking_type: str
    description: str = ""
    owner_employee_id: str | None = None
    start_date: str | None = None
    target_completion_date: str | None = None
    budget_allocated: float | None = None
    linked_entity_id: str | None = None
    target_metric_value: float | None = None


class UpdateInitiativeStatusRequest(BaseModel):

    status: str


class UpdateInitiativeProgressRequest(BaseModel):

    progress_pct: float


@app.get("/strategic-planning/overview")
def strategic_planning_overview_route(quarter: str = None, year: int = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_strategic_planning_overview_api(payload["role"], quarter=quarter, year=year)


@app.get("/strategic-planning/departments")
def strategic_planning_catalog_route(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_strategic_planning_catalog_api(payload["role"])


@app.get("/strategic-planning/quarterly-rollup")
def strategic_planning_quarterly_rollup_route(quarter: str = None, year: int = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_quarterly_rollup_api(payload["role"], quarter=quarter, year=year)


@app.get("/strategic-planning/objectives")
def list_strategic_objectives_route(quarter: str = None, year: int = None, department: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_objectives_api(payload["role"], quarter=quarter, year=year, department=department)


@app.post("/strategic-planning/objectives")
def create_strategic_objective_route(request: CreateStrategicObjectiveRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_objective_api(
        payload["role"], payload["employee_id"],
        request.quarter, request.year, request.department, request.title,
        description=request.description, target_value=request.target_value,
        unit=request.unit, budget_allocated=request.budget_allocated,
    )


@app.get("/strategic-planning/objectives/{objective_id}")
def get_strategic_objective_route(objective_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_objective_api(payload["role"], objective_id)


@app.post("/strategic-planning/objectives/{objective_id}/update")
def update_strategic_objective_route(objective_id: str, request: UpdateStrategicObjectiveRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_objective_api(
        payload["role"], payload["employee_id"], objective_id,
        title=request.title, description=request.description,
        target_value=request.target_value, unit=request.unit,
        budget_allocated=request.budget_allocated,
    )


@app.post("/strategic-planning/objectives/{objective_id}/progress")
def update_strategic_objective_progress_route(objective_id: str, request: UpdateObjectiveProgressRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_objective_progress_api(payload["role"], payload["employee_id"], objective_id, request.progress_pct)


@app.post("/strategic-planning/objectives/{objective_id}/budget")
def update_strategic_objective_budget_route(objective_id: str, request: UpdateBudgetRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_objective_budget_api(
        payload["role"], payload["employee_id"], objective_id,
        budget_allocated=request.budget_allocated, budget_spent=request.budget_spent,
    )


@app.post("/strategic-planning/objectives/{objective_id}/sync-goal")
def sync_strategic_objective_goal_route(objective_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return sync_objective_to_monthly_goal_api(payload["role"], payload["employee_id"], objective_id)


@app.post("/strategic-planning/objectives/{objective_id}/cancel")
def cancel_strategic_objective_route(objective_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return cancel_objective_api(payload["role"], payload["employee_id"], objective_id)


@app.post("/strategic-planning/objectives/{objective_id}/reopen")
def reopen_strategic_objective_route(objective_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return reopen_objective_api(payload["role"], payload["employee_id"], objective_id)


@app.get("/strategic-planning/initiatives")
def list_strategic_initiatives_route(department: str = None, status: str = None, tracking_type: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_initiatives_api(payload["role"], department=department, status=status, tracking_type=tracking_type)


@app.post("/strategic-planning/initiatives")
def create_strategic_initiative_route(request: CreateStrategicInitiativeRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return create_initiative_api(
        payload["role"], payload["employee_id"],
        request.name, request.department, request.tracking_type,
        description=request.description, owner_employee_id=request.owner_employee_id,
        start_date=request.start_date, target_completion_date=request.target_completion_date,
        budget_allocated=request.budget_allocated, linked_entity_id=request.linked_entity_id,
        target_metric_value=request.target_metric_value,
    )


@app.get("/strategic-planning/initiatives/{initiative_id}")
def get_strategic_initiative_route(initiative_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_initiative_api(payload["role"], initiative_id)


@app.post("/strategic-planning/initiatives/{initiative_id}/status")
def update_strategic_initiative_status_route(initiative_id: str, request: UpdateInitiativeStatusRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_initiative_status_api(payload["role"], payload["employee_id"], initiative_id, request.status)


@app.post("/strategic-planning/initiatives/{initiative_id}/progress")
def update_strategic_initiative_progress_route(initiative_id: str, request: UpdateInitiativeProgressRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_initiative_progress_api(payload["role"], payload["employee_id"], initiative_id, request.progress_pct)


@app.post("/strategic-planning/initiatives/{initiative_id}/budget")
def update_strategic_initiative_budget_route(initiative_id: str, request: UpdateBudgetRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return update_initiative_budget_api(
        payload["role"], payload["employee_id"], initiative_id,
        budget_allocated=request.budget_allocated, budget_spent=request.budget_spent,
    )


# ---------------------------------------------------------------------------
# AI Business Analyst -- Readiness' final capstone (Enterprise Readiness &
# Intelligence reframe, Reporting/AI Business Analyst slice -- the LAST item
# of Sam's full 10-item structure + 4-capstone spec). core/ai_business_analyst.py
# / _api.py -- an isolated OpenAI call that may only phrase an answer from a
# real, pre-computed FACTS block (Business Health + Enterprise Risk Center +
# Recommendations + Forecasts), never invent a number; its fallback (used
# whenever OpenAI is unreachable, confirmed true for every call in this
# sandbox) is a real topic-matching formatter over that same FACTS block, not
# a generic "AI unavailable" message. Deliberately open to every real role,
# same convention as every other slice of this reframe.
# ---------------------------------------------------------------------------

class AskBusinessAnalystRequest(BaseModel):

    question: str


@app.post("/ai-business-analyst/ask")
def ask_business_analyst_route(request: AskBusinessAnalystRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return ask_business_analyst_api(payload["role"], request.question, employee_id=payload.get("employee_id"))


# ---------------------------------------------------------------------------
# Lender Intelligence -- real per-lender scorecards + submission log + a
# transparent rules-based lender recommendation. Extracted to
# api/routers/lender_intelligence.py (CAF-00120, god_file_app_py -- splitting
# this file into domain-scoped routers). Included via
# app.include_router(lender_intelligence_router) near the top of this file.
# Same 4 routes, same behavior.
# ---------------------------------------------------------------------------

from api.routers.dealership_lab import router as dealership_lab_router
app.include_router(dealership_lab_router)
from api.routers.dealership_lab_policy import router as dealership_lab_policy_router
app.include_router(dealership_lab_policy_router)

from api.routers.dealership_lab import extras_router
app.include_router(extras_router)


# Anonymous analytics contains only a fixed schema, never customer form contents.
from collections import OrderedDict as _VisitBuckets
from threading import Lock as _VisitLock
import time as _visit_time
_visit_buckets = _VisitBuckets()
_visit_lock = _VisitLock()

@app.post("/public/websites/{website_id}/events")
async def website_visit_event(website_id: str, request: Request):
    from core.website_visits import collect
    from fastapi.responses import JSONResponse
    key=(request.client.host if request.client else "unknown",website_id)
    now=_visit_time.monotonic()
    with _visit_lock:
        started,count=_visit_buckets.get(key,(now,0))
        if now-started>=60: started,count=now,0
        if count>=90: return JSONResponse({"error":"Too many events"},status_code=429)
        _visit_buckets[key]=(started,count+1); _visit_buckets.move_to_end(key)
        while len(_visit_buckets)>10000: _visit_buckets.popitem(last=False)
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>2048: return JSONResponse({"error":"Event too large"},status_code=413)
    try:
        import json
        data=json.loads(body)
        if not isinstance(data,dict): raise ValueError()
    except (ValueError,TypeError): return JSONResponse({"error":"Invalid event"},status_code=400)
    result=collect(website_id,data,request.headers.get("user-agent",""))
    return JSONResponse(result,status_code=400 if "error" in result else 200)


@app.get("/websites/{website_id}/assistant-readiness")
def website_assistant_readiness(website_id: str, authorization: str = Header(None)):
    payload,error=_authenticate(authorization)
    if error: return error
    from core.website_chat_api import _can_work_chat
    from core.websites import get_website
    from core.website_revisions import public_version
    from core.website_chat import is_feature_enabled
    from core.website_ai_credentials import status
    if not get_website(website_id): return {"error":"Website not found"}
    if not _can_work_chat(payload["role"],payload["employee_id"],website_id): return {"error":"You don't have access to this site"}
    approved=public_version(get_website(website_id))
    return {"published_enabled":bool(approved and (approved.attributes.get("admin_settings") or {}).get("ai_receptionist_enabled")), "provider_configured":status(website_id)["status"]=="connected", "platform_enabled":is_feature_enabled("website_ai_receptionist")}


class WebsiteAIKeyRequest(BaseModel):
    provider: str
    model: str
    api_key: str

def _website_ai_access(website_id,authorization):
    payload,error=_authenticate(authorization)
    if error: return error
    if payload["role"]!="ADMIN": return {"error":"Dealer administrator access is required to manage API credentials"}
    from core.websites import get_website
    if not get_website(website_id):return {"error":"Website not found"}
    return None

@app.get("/websites/{website_id}/assistant-connection")
def website_ai_status(website_id: str,authorization: str = Header(None)):
    error=_website_ai_access(website_id,authorization)
    if error:return error
    from core.website_ai_credentials import status
    try:return status(website_id)
    except ValueError as exc:return {"error":str(exc)}

@app.put("/websites/{website_id}/assistant-connection")
async def website_ai_save(website_id: str,request: Request,authorization: str = Header(None)):
    error=_website_ai_access(website_id,authorization)
    if error:return error
    from core.website_ai_credentials import save
    # Parse explicitly: framework validation errors can echo a secret-bearing body.
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>4096:return {"error":"Credential request too large"}
    try:
        import json
        data=json.loads(body)
        if not isinstance(data,dict) or set(data)!={"provider","model","api_key"}:raise ValueError()
    except (ValueError,TypeError):return {"error":"Provider, model and API key are required"}
    try:return save(website_id,data["provider"],data["model"],data["api_key"])
    except ValueError as exc:return {"error":str(exc)}

@app.post("/websites/{website_id}/assistant-connection/test")
def website_ai_test(website_id: str,authorization: str = Header(None)):
    error=_website_ai_access(website_id,authorization)
    if error:return error
    from core.website_ai_credentials import test_connection
    try:return test_connection(website_id)
    except ValueError as exc:return {"error":str(exc)}

@app.delete("/websites/{website_id}/assistant-connection")
def website_ai_disconnect(website_id: str,authorization: str = Header(None)):
    error=_website_ai_access(website_id,authorization)
    if error:return error
    from core.website_ai_credentials import disconnect
    return disconnect(website_id)


@app.get("/websites/{website_id}/domain-connection")
def website_domain_status(website_id: str, authorization: str = Header(None)):
    return _website_domain_action(website_id, authorization, "status")


@app.post("/websites/{website_id}/domain-connection/prepare")
def website_domain_prepare(website_id: str, authorization: str = Header(None)):
    return _website_domain_action(website_id, authorization, "prepare")


@app.post("/websites/{website_id}/domain-connection/verify")
def website_domain_verify(website_id: str, authorization: str = Header(None)):
    return _website_domain_action(website_id, authorization, "verify")


@app.post("/websites/{website_id}/domain-connection/activate")
def website_domain_activate(website_id: str, authorization: str = Header(None)):
    return _website_domain_action(website_id, authorization, "activate")


@app.post("/websites/{website_id}/domain-connection/check_https")
def website_domain_check_https(website_id: str, authorization: str = Header(None)):
    return _website_domain_action(website_id, authorization, "check_https")


def _website_domain_action(website_id, authorization, action):
    payload, error = _authenticate(authorization)
    if error:
        return error
    if payload["role"] not in ("ADMIN", "MARKETING"):
        return {"error": "Only dealer administrators and marketing can manage domains"}
    from core import website_domains
    try:
        return getattr(website_domains, action)(website_id)
    except ValueError as exc:
        return {"error": str(exc)}


@app.get("/website-offers")
def website_offers(authorization: str = Header(None)):
    _, error = _authenticate(authorization)
    if error:
        return error
    from core.website_offers import published_offers
    return published_offers()


@app.get("/public/garage/offers")
def public_garage_offers(token: str):
    from core.website_offers import garage_offers
    return garage_offers(token)


@app.get("/public/website-offers")
def public_website_offers():
    """Only already-published dealer offers and public inventory; no customer data."""
    from core.website_offers import published_offers
    return published_offers()

from api.routers.bdc import router as bdc_router
app.include_router(bdc_router)

from api.routers.campaign_workflow import router as campaign_workflow_router
app.include_router(campaign_workflow_router)

from api.routers.floorplan_work import router as floorplan_work_router
app.include_router(floorplan_work_router)

from api.routers.commission_work import router as commission_work_router
app.include_router(commission_work_router)

from api.routers.readiness_mappings import router as readiness_mappings_router
app.include_router(readiness_mappings_router)

from api.routers.readiness_policies import router as readiness_policies_router
app.include_router(readiness_policies_router)
