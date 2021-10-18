from charms.reactive import Endpoint, when, set_flag, clear_flag
import charmhelpers.core.hookenv as hookenv
from charmhelpers.core.hookenv import log

class GearmanRequires(Endpoint):

    @when('endpoint.{endpoint_name}.joined')
    def joined(self):
        # if any(unit.received['port'] for unit in self.all_joined_units):
        set_flag(self.expand_name('available'))

    @when('endpoint.{endpoint_name}.changed')
    def changed(self):
        # if any(unit.received['port'] for unit in self.all_joined_units):
        set_flag(self.expand_name('available'))

    def address(self):
        """Get the address to access Gearman over."""
        for relation in self.relations:
            for unit in relation.joined_units:
                log("Unit: {}".format(unit.received))
                address = unit.ingress_address
                if address is not None:
                    return address
