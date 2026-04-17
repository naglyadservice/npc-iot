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
