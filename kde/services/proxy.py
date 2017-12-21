import logging
import os
from service import Service
from kde.util import common
from kde.templates import constants

tmp_dir = constants.tmp_kde_dir
k8s_ssl_dir = constants.k8s_ssl_dir
tmp_bin_dir = constants.tmp_bin_dir


class Proxy(Service):
    def __init__(self):
        super(Proxy,self).__init__()
        self.service_name = "kube-proxy"

    def configure(self,**cluster_data):
        k8s_configs = cluster_data.get("kubernetes")

        self.cluster_cidr = k8s_configs.get("cluster_cidr")
        #
        # nodes = cluster_data.get('nodes')
        #
        # for node in nodes:
        #     if 'worker' in node.get('role'):
        #         self.nodes.append(node)

    def _deploy_service(self):
        # for node in self.nodes:
        #     ip = node.get('external_IP')
        #     user = node.get('ssh_user')
        #     password = node.get("ssh_password")
        #     name = node.get("hostname")

        logging.info("Starting To Deploy kube-proxy On Node: %s, IP address: %s ", self.host_name, self.node_ip)

        common.render(os.path.join(constants.template_dir, "kube-proxy.service"),
                      os.path.join(tmp_dir, "kube-proxy.service"),
                      node_ip=self.node_ip,
                      cluster_cidr=self.cluster_cidr,
                      )

        logging.info("Copy kube-proxy Config Files To Node: " + self.host_name)

        rsh = self.remote_shell
        # rsh.connect()

        rsh.copy(tmp_bin_dir+"kube-proxy","/usr/bin/")
        rsh.copy(tmp_dir + "admin.kubeconfig", "/etc/kubernetes/")
        rsh.copy(tmp_dir + "kube-proxy.service", "/etc/systemd/system/")

        rsh.execute("systemctl enable kube-proxy")

        # rsh.close()

