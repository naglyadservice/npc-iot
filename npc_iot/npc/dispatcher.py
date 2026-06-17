import logging

from ..base.dispatcher import BaseDispatcher, MessageHandler

log = logging.getLogger(__name__)


class NpcDispatcher(BaseDispatcher):
    begin = MessageHandler("/{device_id}/server/begin")
    reboot_ack = MessageHandler("/{device_id}/server/reboot/ack", is_ack=True)
    config_ack = MessageHandler("/{device_id}/server/config/ack", is_ack=True)
    config = MessageHandler("/{device_id}/server/config")
    setting_ack = MessageHandler("/{device_id}/server/setting/ack", is_ack=True)
    setting = MessageHandler("/{device_id}/server/setting")
    state_ack = MessageHandler("/{device_id}/server/state/ack", is_ack=True)
    state = MessageHandler("/{device_id}/server/state", is_result=True)
    state_info = MessageHandler("/{device_id}/server/state/info")
    phone_add_multi_ack = MessageHandler("/{device_id}/phone/add_multi/ack", is_ack=True)
    phone_del_ack = MessageHandler("/{device_id}/phone/del/ack", is_ack=True)

    # --- N-GATE v2.0: presence, DB sync, history, realtime events, rule config ---
    status = MessageHandler("/{device_id}/server/status")
    db_delta_ack = MessageHandler("/{device_id}/server/db/delta/ack", is_ack=True)
    db_reset_ack = MessageHandler("/{device_id}/server/db/reset/ack", is_ack=True)
    db_stats = MessageHandler("/{device_id}/server/db/stats")
    history = MessageHandler("/{device_id}/server/history")
    event = MessageHandler("/{device_id}/server/event")
    rule_ack = MessageHandler("/{device_id}/server/rule/ack", is_ack=True)
