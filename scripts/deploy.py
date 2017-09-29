#!/usr/bin/python
# -*- coding: utf-8 -*-


from __future__ import print_function, unicode_literals  # We require Python 2.6 or later
from string import Template
import random
import string
import socket
import os
import sys
import argparse
import subprocess
import shutil
import base64
from io import open

if sys.version_info[:3][0] == 2:
    import ConfigParser as ConfigParser
    import StringIO as StringIO

if sys.version_info[:3][0] == 3:
    import configparser as ConfigParser
    import io as StringIO

#------Global Vars-----

base_dir = os.path.dirname(__file__)
FNULL = open(os.devnull,'w')

parser = argparse.ArgumentParser()

# --- args ---
parser.add_argument('--conf', dest='cfgfile', default=base_dir + '/k8s.cfg', type=str,
                    help="the path of Kubernetes configuration file")
parser.add_argument('--host-ip',dest='host_ip',type=str,help="Host IP Address")
parser.add_argument('--role',dest='node_role',type=str,default='',require=True,help="Node Role Type:master/minion")
parser.add_argument('--test',dest='test_unit',type=str,default='')
args = parser.parse_args()

# --- confs ---
conf = StringIO.StringIO()
conf.write("[configuration]\n")
conf.write(open(args.cfgfile).read())
conf.seek(0, os.SEEK_SET)
rcp = ConfigParser.RawConfigParser()
rcp.readfp(conf)

# --- vars ---
node_name = socket.gethostname()
if args.host_ip:
    node_ip= args.host_ip
else:
    node_ip = rcp.get("configuration", "node_ip")

master_ip = rcp.get("configuration", "master_ip")
kube_apiserver = "https://"+master_ip+":6443"
cluster_kubernetes_svc_ip = rcp.get("configuration", "cluster_kubernetes_svc_ip")
cluster_dns_domain = rcp.get("configuration", "cluster_dns_domain")
cluster_dns_svc_ip =rcp.get("configuration", "cluster_dns_svc_ip")
node_port_range =rcp.get("configuration", "node_port_range")
cluster_cidr =rcp.get("configuration", "cluster_cidr")
service_cidr =rcp.get("configuration", "service_cidr")

bootstrap_token=  rcp.get("configuration", "bootstrap_token")

#     ----config dest folders----

template_dir = os.path.join(base_dir,"templates")
systemd_dir = "/etc/systemd/system/"
etcd_ssl_dir = "/etc/etcd/ssl/"
k8s_ssl_dir = "/etc/kubernetes/ssl/"


#------ Functions: Utilities ------

def prep_conf_dir(root, name):
    absolute_path = os.path.join(root, name)
    if not os.path.exists(absolute_path):
        os.makedirs(absolute_path)
    return absolute_path

def render(src, dest, **kw):
    t = Template(open(src, 'r').read())
    if not os.path.exists(dest):
        os.mknod(dest)
    with open(dest, 'w') as f:
        f.write(t.substitute(**kw))
    print("Generated configuration file: %s" % dest)

def get_binaries():
    subprocess.call(["bash", "-c", "./get-binaries.sh"])

def generate_cert():

    prep_conf_dir(etcd_ssl_dir,'')
    prep_conf_dir(k8s_ssl_dir,'')
    render(os.path.join(template_dir,"etcd-csr.json"),
           os.path.join(etcd_ssl_dir,"etcd-csr.json"),
           node_name=node_name,
           node_ip=node_ip)
    render(os.path.join(template_dir,"kubernetes-csr.json"),
           os.path.join(k8s_ssl_dir,"kubernetes-csr.json"),
           node_name=node_name,
           node_ip=node_ip,
           master_ip=master_ip,
           cluster_kubernetes_svc_ip=cluster_kubernetes_svc_ip)
    render(os.path.join(template_dir,"token.csv"),
           os.path.join("/etc/kubernetes/","token.csv"),
           bootstrap_token=bootstrap_token)

    subprocess.call(["bash","-c", os.path.join(base_dir,"util","generate_cert.sh")])

def generate_kubeconfig():
    subprocess.call(["bash", "-c", os.path.join(base_dir, "util", "generate_kubeconfig.sh",kube_apiserver,bootstrap_token)])

def get_cert_from_master():
    pass


#------ Functions: Deployment Actions ------
def config_etcd():
    print('------Configurating Etcd------')
    prep_conf_dir("/var/lib/etcd",'')
    discovery = subprocess.check_output(["curl", "-s", "https://discovery.etcd.io/new?size=1"])

    render(os.path.join(template_dir,"etcd.service"),
           os.path.join(systemd_dir,"etcd.service"),
           node_ip=node_ip,
           node_name=node_name,
           discovery=discovery.replace('https','http'))

def config_flannel():
    print('------Configurating Flannel------')

    render(os.path.join(template_dir,"flanneld.service"),
           os.path.join(systemd_dir, "flanneld.service"),
           master_ip=master_ip)

def config_kubelet():
    print('------Configurating kubelet------')

def config_apiserver():
    print('------Configurating kube-apiserver ------')

def config_controller_manager():
    print('------Configurating kube-controller-manager ------')

def config_scheduler():
    print('------Configurating kube-scheduler ------')

def config_addons():
    print('------Configurating Addons:kube-dns ------')


#------ Deployment Start ------

role = args.node_role

if args.test_unit:
    print('------Script Testing------')
else:
    get_binaries()
    generate_cert()


    if role == 'master':
        config_etcd()
        config_flannel()
        config_kubelet()
        config_apiserver()
        config_controller_manager()
        config_scheduler()
        config_addons()

        subprocess.call(["systemctl", "daemon-reload"])

        print("Starting Etcd...")
        subprocess.call(["systemctl", "start", "etcd"])
        print("Starting Etcd...")
        subprocess.call(["systemctl", "start", "flanneld"])
        print("Starting Docker...")
        subprocess.call(["systemctl", "restart", "docker"])
        print("Starting kubelet...")
        subprocess.call(["systemctl", "start", "kubelet"])
        print("Starting kube-apiserver...")
        subprocess.call(["systemctl", "start", "kube-apiserver"])
        print("Starting kube-controller-manager...")
        subprocess.call(["systemctl", "start", "kube-controller-manager"])
        print("Starting kube-scheduler...")
        subprocess.call(["systemctl", "start", "kube-scheduler"])
        # subprocess.call(["systemctl", "start", ""])

    if role == 'minion':
        get_cert_from_master()














