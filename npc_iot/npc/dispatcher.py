import logging

from ..base.dispatcher import BaseDispatcher, MessageHandler

log = logging.getLogger(__name__)


class NpcDispatcher(BaseDispatcher):
    begin = MessageHandler(topic="/+/server/begin")
    reboot_ack = MessageHandler(topic="/+/server/reboot/ack", is_ack=True)
    config_ack = MessageHandler(topic="/+/server/config/ack", is_ack=True)
    config = MessageHandler(topic="/+/server/config")
    setting_ack = MessageHandler(topic="/+/server/setting/ack", is_ack=True)
    setting = MessageHandler(topic="/+/server/server/setting")
    state_ack = MessageHandler(topic="/+/server/state/ack", is_ack=True)
    state = MessageHandler(topic="/+/server/state", is_result=True)
    state_info = MessageHandler(topic="/+/server/state/info")
    phone_add_multy_ack = MessageHandler("/+/phone/add_multy/ack", is_ack=True)
    phone_del_ack = MessageHandler("/+/phone/del/ack", is_ack=True)
