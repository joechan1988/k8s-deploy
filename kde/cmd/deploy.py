import os
import logging
import string
import multiprocessing
import auth
import random
import datetime
from kde.util import common, cert_tool, config_parser
from kde.templates import constants, json_schema
from kde.util.common import RemoteShell
from kde.util.exception import *
from kde.services import *


def _get_host_time(ip=None, user=None, password=None):
    if ip is not None \
            and user is not None \
            and password is not None:
        rsh = RemoteShell(ip, user, password)
        rsh.connect()

        ret = rsh.execute("date +'%Y-%m-%d %H:%M:%S'")
        rsh.close()

        date_time = datetime.datetime.strptime(ret[0].replace("\n", ""), '%Y-%m-%d %H:%M:%S')

        return date_time

    else:
        ret = common.shell_exec("date +'%Y-%m-%d %H:%M:%S'", shell=True, output=True)
        date_time = datetime.datetime.strptime(ret.replace("\n", ""), '%Y-%m-%d %H:%M:%S')

        return date_time


def _check_host_time(cluster_data):
    nodes = cluster_data.get("nodes")

    pool = multiprocessing.Pool(len(nodes))
    pool_results = list()
    host_time_list = list()
    for node in nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        ret = pool.apply_async(_get_host_time, args=(ip, user, password))

        pool_results.append(ret)

    pool.close()
    pool.join()

    for pool_result in pool_results:
        host_time_list.append(pool_result.get())

    host_time_diff = 0
    host_time_base = _get_host_time()
    # print(host_time_list)
    for host_time in host_time_list:
        host_time_diff = (host_time - host_time_base).seconds if host_time > host_time_base \
            else (host_time_base - host_time).seconds

    if host_time_diff > 60:
        return False
    else:
        return True


def pre_check(cluster_data, check_leftover):
    """
    Environment check before starting deployment procedure.

    :param cluster_data:  cluster.yml data
    :param rsh:  Remote Shell Obj to connect ssh to node
    :return: result dict
                result:  "passed" or "failed"
                hint: detailed message
    """

    summary = dict({"result": "",
                    "nodes": [
                        # {
                        #     "name": "",
                        #     "passed": "",
                        #     "details": ""
                        # }
                    ],
                    "message": ""
                    })

    nodes = cluster_data.get("nodes")

    docker_version_cmd = "docker version --format {{.Server.Version}}"
    leftover_dirs_check_list = ["/var/lib/kubelet/",
                                "/etc/kubernetes/",
                                "/var/lib/etcd/"
                                ]

    for node in nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        node_result = {
            "name": name,
            "passed": "",
            "details": ""
        }

        # SSH Connection Reachability Check
        rsh = RemoteShell(ip, user, password)
        if rsh.connect() == False:
            summary["result"] = "failed"
            summary["hint"] = "Node {" + name + "}(IP: " + ip + ") is NOT reachable. Check SSH connectivity"
            continue

        # Essential module check: systemctl, nslookup ...

        essential_bins = ["systemctl", "docker", "sysctl", "jq"]
        recommended_bins = ['nslookup', 'conntrack']

        for bin_name in essential_bins:
            check_result = rsh.check_module(bin_name)
            if not check_result:
                node_result["passed"] = "no"
                node_result["details"] = node_result["details"] + "Module or component {0} is not found.".format(
                    bin_name)

        for bin_name in recommended_bins:
            check_result = rsh.check_module(bin_name)
            if not check_result:
                logging.warning("Warning: Module or component {0} is not found.".format(bin_name))
                node_result["details"] = node_result["details"] + "Module or component {0} is not found.".format(
                    bin_name)

        # ---Docker Version Check ---
        docker_version = rsh.execute(docker_version_cmd)

        if "Cannot connect to the Docker daemon" in docker_version[0]:
            node_result["passed"] = "no"
            node_result["details"] = node_result["details"] + "Docker daemon is probably not running. "
        elif "1.12" not in docker_version[0] \
            or "1.11" not in docker_version[0] \
            or "1.10" not in docker_version[0]:
            node_result["passed"] = "no"
            node_result["details"] = node_result["details"] + "Incompatible docker version; "

        # ---Left-over Directories Check ---
        leftover_dirs = list([])
        leftover_dir_names = ""

        for directory in leftover_dirs_check_list:
            out = rsh.execute("ls -l " + directory)
            if "No such file or directory" not in out[0] and "total 0" not in out[-1]:
                leftover_dirs.append(directory)
                leftover_dir_names = leftover_dir_names + directory + ", "

        if len(leftover_dirs):
            if check_leftover:
                node_result["passed"] = "no"
            else:
                node_result["passed"] = "yes"

            node_result["details"] = node_result["details"] + "Fount non-empty directories: {0} ;".format(
                leftover_dir_names, name)

        # --- Etcd left-over container check ---

        if "etcd" in node.get("role"):
            out = rsh.execute("docker ps -a|grep kde-etcd")
            if len(out):
                node_result["passed"] = "no"
                node_result["details"] = node_result["details"] + "Existing etcd containers found; "

        # --- IPV4 Forwarding Check ---
        ipv4_forward_check = rsh.execute("sysctl net.ipv4.conf.all.forwarding -b")
        if ipv4_forward_check[0] != "1":
            node_result["passed"] = "no"
            node_result["details"] = node_result["details"] + "IPV4 Forwarding Is Disabled; "

        # ---- SELinux check ---
        selinux_check = rsh.execute("getenforce")
        if "Enforcing" in selinux_check[0]:
            node_result["passed"] = "no"
            node_result["details"] = node_result["details"] + "SElinux is set Enabled; "

        rsh.close()

        summary["nodes"].append(node_result)

    # Summary nodes check result

    for node_result in summary["nodes"]:
        if node_result["passed"] == "no":
            summary["result"] = "failed"
            summary["message"] = "Environment check on node '{node_name}' " \
                                 "failed. Details: {details} ".format(
                node_name=node_result["name"],
                details=node_result["details"])
            break

    # host time synchronization check

    if not _check_host_time(cluster_data):
        summary["result"] = "failed"
        summary["message"] = summary["message"] + \
                             "Time settings difference between nodes is larger than 1 minutes.Check ntp service installation. "

    if summary["result"] == "failed":
        raise PreCheckError(summary["message"])
    else:
        summary["result"] = "passed"

    return summary


def prep_binaries(path, cluster_data):
    """
    Prepare binaries for local start.
    Could be rpm-installed or ftp downloaded.
    For ftp instance, ftp address and list of binaries should be defined in cluster.yml
    :return:
    """

    bin_list = cluster_data.get("binaries").get("list")
    redownload_flag = cluster_data.get("binaries").get("redownload")

    if redownload_flag == "yes":

        dl_path = cluster_data.get("binaries").get("download_url")
        urls = []
        for binary in bin_list:
            urls.append(dl_path + binary)

        common.prep_conf_dir(path, "", clear=True)
        common.download_binaries(urls, path)

    elif redownload_flag == "no":
        for binary in bin_list:
            if not common.check_binaries(path, binary):
                raise BinaryNotFoundError(binary, path)

    else:
        raise ClusterConfigError("Config field <binaries.redownload> is malformed")

    common.shell_exec("\cp -f " + path + "kubectl /usr/bin/", shell=True)


def _deploy_node(ip, user, password, hostname, service_list, **cluster_data):
    rsh = RemoteShell(ip, user, password)
    rsh.connect()

    result = {
        "node": hostname,
        "ip": ip,
        "result": "",
        "failed_service": []
    }

    for service in service_list:
        service.remote_shell = rsh
        service.node_ip = ip
        service.host_name = hostname
        # service.configure(**cluster_data)
        service.deploy()
        ret = service.start()
        if not ret:
            result["failed_service"].append(service.service_name)

    rsh.prep_dir("/root/.kube/")
    rsh.copy(constants.kde_auth_dir + "admin.kubeconfig", "/root/.kube/config")

    if len(result["failed_service"]) != 0:
        result["result"] = "failure"
    else:
        result["result"] = "success"

    rsh.close()

    return result


def _reset_node(ip, user, password, hostname, service_list, **cluster_data):
    clean_up_dirs = ["/var/lib/kubelet/", "/etc/kubernetes/"]

    rsh = RemoteShell(ip, user, password)
    rsh.connect()

    for service in service_list:
        service.remote_shell = rsh
        service.node_ip = ip
        service.host_name = hostname
        service.stop()


def do(cluster_data):
    """
    Deployment order: etcd node > control node > worker node;

    :param cluster_data:
    :return:
    """

    results = {
        "summary": "failure",  # success or failure
        "nodes": [
            # {
            #     "node_name": "",
            #     "node_ip": "",
            #     "result": "failure"
            # }
        ]
    }

    def _sum_results(results_dict):
        for item in results_dict["nodes"]:
            if item["result"] == "failure":
                results_dict["summary"] = "failure"
                return
        results_dict["summary"] = "success"

    logging.critical("Starting environment precheck...")
    try:
        # validate_cluster_data(cluster_data)
        precheck_result = pre_check(cluster_data, check_leftover=False)
    except BaseError as e:
        logging.error(e.message)
        return
    if precheck_result is not None:
        logging.info("Environment check result: " + precheck_result["result"])

    # Prepare local temp directory

    kde_auth_dir = constants.kde_auth_dir
    common.prep_conf_dir(kde_auth_dir, "", clear=True)
    common.prep_conf_dir(constants.kde_service_dir, "", clear=True)

    # Group node by control and worker
    control_nodes = list()
    worker_nodes = list()
    etcd_nodes = list()
    nodes = cluster_data.get("nodes")

    for node in nodes:
        if "control" in node.get('role'):
            control_nodes.append(node)
        if "worker" in node.get('role'):
            worker_nodes.append(node)
        if "etcd" in node.get('role'):
            etcd_nodes.append(node)

    if len(control_nodes) == 0 or len(etcd_nodes) == 0:
        raise ClusterConfigError("Initiated cluster should at least have 1 control node and 1 etcd node")

    # Get CNI type
    cni_plugin = cluster_data.get("cni").get("plugin")

    # Prepare binaries to temp directory

    tmp_bin_path = cluster_data.get("binaries").get("path")
    try:
        prep_binaries(tmp_bin_path, cluster_data)
    except BaseError as e:
        logging.error(e.message)

    # Generate CA cert to temp directory
    auth.generate_ca_cert(kde_auth_dir)

    # Generate Bootstrap Token to temp directory
    auth.generate_bootstrap_token(kde_auth_dir)

    # Generate k8s & etcd cert files to temp directory

    auth.generate_etcd_cert(kde_auth_dir, cluster_data)
    auth.generate_apiserver_cert(kde_auth_dir, cluster_data)
    auth.generate_admin_kubeconfig(cluster_data)

    # Start deployment process:

    docker = Docker()
    apiserver = Apiserver()
    cmanager = CManager()
    scheduler = Scheduler()
    proxy = Proxy()
    etcd = Etcd()
    kubelet = Kubelet()
    calico = Calico()

    total_service_list = [docker, apiserver, cmanager, scheduler, proxy, etcd, kubelet, calico]
    for service in total_service_list:
        service.configure(**cluster_data)

        # Attempt to deploy etcd node

    for node in etcd_nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        service_list = [docker, etcd]
        result = _deploy_node(ip, user, password, name, service_list, **cluster_data)
        results["nodes"].append(result)

        # Summary Etcd node deploy results.If failure, stop the whole deployment
    _sum_results(results)
    if results["summary"] == "failure":
        return results

        # Attempt to deploy controller node
    for node in control_nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        if node in etcd_nodes:
            service_list = [apiserver, cmanager, scheduler, kubelet, proxy]
        else:
            service_list = [docker, apiserver, cmanager, scheduler, kubelet, proxy]

        result = _deploy_node(ip, user, password, name, service_list, **cluster_data)
        results["nodes"].append(result)

        if result["result"] == "success":
            common.shell_exec("kubectl label node " + ip + " node-role.kubernetes.io/master=", shell=True)

            # Summary controller node deploy results.If failure, stop the whole deployment
    _sum_results(results)
    if results["summary"] == "failure":
        return results

        # Attempt to deploy worker node
    for node in worker_nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        if node in etcd_nodes:
            service_list = [kubelet, proxy]
        else:
            service_list = [docker, kubelet, proxy]

        result = _deploy_node(ip, user, password, name, service_list, **cluster_data)
        results["nodes"].append(result)

        # Attempt to deploy CNI plugin
    if cni_plugin == "calico":
        for node in control_nodes:
            ip = node.get('external_IP')
            user = node.get('ssh_user')
            password = node.get("ssh_password")
            name = node.get("hostname")

            service_list = [calico]
            result = _deploy_node(ip, user, password, name, service_list, **cluster_data)
            if result["result"] == "failure":
                logging.error(
                    "Failed to deploy calico cni plugin on node: {0}. Please try deploying it manually.".format(name))

            break

    _sum_results(results)

    # save ca,cert files to k8s cluster

    save_cert_cmd = "kubectl -n kube-system create secret generic k8s-cert-bak \
                                --from-file=ca=" + kde_auth_dir + "ca.pem \
                                --from-file=cert=" + kde_auth_dir + "kubernetes.pem \
                                --from-file=key=" + kde_auth_dir + "kubernetes-key.pem"

    common.shell_exec(save_cert_cmd, shell=True)

    return results


def reset(cluster_data, clear=False):
    """
    Reset the last deployment

    :return:
    """

    # Stop all services
    # Unmount pods volumes
    # Clear the temp directories
    # Restart docker daemon

    logging.critical("Starting to clean up the last cluster deployment...")

    docker = Docker()
    apiserver = Apiserver()
    cmanager = CManager()
    scheduler = Scheduler()
    proxy = Proxy()
    etcd = Etcd()
    kubelet = Kubelet()

    control_nodes = list()
    worker_nodes = list()
    etcd_nodes = list()
    nodes = cluster_data.get("nodes")
    for node in nodes:
        if "control" in node.get('role'):
            control_nodes.append(node)
        if "worker" in node.get('role'):
            worker_nodes.append(node)
        if "etcd" in node.get('role'):
            etcd_nodes.append(node)

    for node in control_nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        rsh = RemoteShell(ip, user, password)
        rsh.connect()

        service_list = [docker, apiserver, cmanager, scheduler, kubelet, proxy]

        for service in service_list:
            service.remote_shell = rsh
            service.host_name = name
            service.stop()
            rsh.execute("systemctl disable " + service.service_name)

        if clear:
            rsh.execute("umount /var/lib/kubelet/pods/*/volumes/*/*")
            rsh.execute("rm -rf /var/lib/kubelet/ /etc/kubernetes/")

        docker.start()
        rsh.close()

    for node in etcd_nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")
        rsh = RemoteShell(ip, user, password)
        rsh.connect()

        service_list = [etcd]
        for service in service_list:
            service.host_name = name
            service.remote_shell = rsh
            service.stop()
            # rsh.execute("systemctl disable " + service.service_name)

        bak_dir_name = "etcd_bak_" + "".join(random.sample(string.ascii_letters + string.digits, 8))
        rsh.execute("mv /var/lib/etcd/ /var/lib/" + bak_dir_name + "/")

    for node in worker_nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        rsh = RemoteShell(ip, user, password)
        rsh.connect()

        service_list = [docker, kubelet, proxy]

        for service in service_list:
            service.remote_shell = rsh
            service.stop()
            rsh.execute("systemctl disable " + service.service_name)

        if clear:
            rsh.execute("umount /var/lib/kubelet/pods/*/volumes/*/*")
            rsh.execute("rm -rf /var/lib/kubelet/ /etc/kubernetes/")

        docker.start()
        rsh.close()

    logging.critical("Clean-up job finished.")


def add_host(cluster_data):
    """
    Add new hosts to a existing kubernetes cluster

    :return:
    """
    logging.critical("Adding new hosts to the initiated cluster...")

    admin_kubeconfig_path = cluster_data.get("admin_kubeconfig")
    if admin_kubeconfig_path is None:
        raise ClusterConfigError("Admin kubeconfig file path is misconfigured")
    if not os.path.exists(admin_kubeconfig_path):
        raise ClusterConfigError("Admin kubeconfig file not found in configured path")

    if admin_kubeconfig_path != constants.kde_auth_dir + "admin.kubeconfig":
        common.shell_exec("cp -f {0} {1}".format(admin_kubeconfig_path, constants.kde_auth_dir + "admin.kubeconfig"))

    results = {
        "summary": "failure",  # success or failure
        "nodes": [
            # {
            #     "node_name": "",
            #     "node_ip": "",
            #     "result": "failure"
            # }
        ]
    }

    def _sum_results(results_dict):
        for item in results_dict["nodes"]:
            if item["result"] == "failure":
                results_dict["summary"] = "failure"
                return
        results_dict["summary"] = "success"

    logging.critical("Starting environment precheck...")
    try:
        # validate_cluster_data(cluster_data)
        precheck_result = pre_check(cluster_data, check_leftover=False)
    except BaseError as e:
        logging.error(e.message)
        return
    if precheck_result is not None:
        logging.info("Environment check result: " + precheck_result["result"])

    # Prepare local temp directory

    kde_auth_dir = constants.kde_auth_dir

    # Group node by control and worker
    control_nodes = list()
    worker_nodes = list()
    # etcd_nodes = list()
    nodes = cluster_data.get("nodes")

    for node in nodes:
        if "control" in node.get('role'):
            control_nodes.append(node)
        if "worker" in node.get('role'):
            worker_nodes.append(node)

    # Check kde config files; if not exists, recover from k8s cluster
    if len(control_nodes) > 0:
        if (not os.path.exists(constants.kde_auth_dir + "ca.pem") or
                not os.path.exists(constants.kde_auth_dir + "kubernetes-key.pem") or
                not os.path.exists(constants.kde_auth_dir + "kubernetes.pem")):
            common.prep_conf_dir(constants.kde_auth_dir, "", clear=False)

            recover_cmd0 = """ kubectl -n kube-system get secret k8s-cert-bak -o json \
                                    |jq '.data.\"ca\"'   \
                                    | sed 's/\"//g'| base64 --decode >{0} """.format(
                constants.kde_auth_dir + "ca.pem")
            recover_cmd1 = """ kubectl -n kube-system get secret k8s-cert-bak -o json \
                                    |jq '.data.\"cert\"'   \
                                    | sed 's/\"//g'| base64 --decode >{0} """.format(
                constants.kde_auth_dir + "kubernetes.pem")
            recover_cmd2 = """ kubectl -n kube-system get secret k8s-cert-bak -o json \
                                    |jq '.data.\"key\"'   \
                                    | sed 's/\"//g'| base64 --decode >{0} """.format(
                constants.kde_auth_dir + "kubernetes-key.pem")

            common.shell_exec(recover_cmd0, shell=True)
            common.shell_exec(recover_cmd1, shell=True)
            common.shell_exec(recover_cmd2, shell=True)

    # Get CNI type
    cni_plugin = cluster_data.get("cni").get("plugin")

    # Prepare binaries to temp directory

    tmp_bin_path = cluster_data.get("binaries").get("path")
    try:
        prep_binaries(tmp_bin_path, cluster_data)
    except BaseError as e:
        logging.error(e.message)

    # Start deployment process:

    docker = Docker()
    apiserver = Apiserver()
    cmanager = CManager()
    scheduler = Scheduler()
    proxy = Proxy()
    etcd = Etcd()
    kubelet = Kubelet()
    calico = Calico()

    total_service_list = [docker, apiserver, cmanager, scheduler, proxy, etcd, kubelet, calico]
    for service in total_service_list:
        service.configure(**cluster_data)

        # Attempt to deploy controller node
    for node in control_nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        service_list = [docker, apiserver, cmanager, scheduler, kubelet, proxy]
        result = _deploy_node(ip, user, password, name, service_list, **cluster_data)
        results["nodes"].append(result)

        if result["result"] == "success":
            common.shell_exec("kubectl label node " + ip + " node-role.kubernetes.io/master=", shell=True)

            # Summary controller node deploy results.If failure, stop the whole deployment
    _sum_results(results)
    if results["summary"] == "failure":
        return results

        # Attempt to deploy worker node
    for node in worker_nodes:
        ip = node.get('external_IP')
        user = node.get('ssh_user')
        password = node.get("ssh_password")
        name = node.get("hostname")

        service_list = [docker, kubelet, proxy]

        result = _deploy_node(ip, user, password, name, service_list, **cluster_data)
        results["nodes"].append(result)

        # Attempt to deploy CNI plugin
    if cni_plugin == "calico":
        for node in control_nodes:
            ip = node.get('external_IP')
            user = node.get('ssh_user')
            password = node.get("ssh_password")
            name = node.get("hostname")

            service_list = [calico]
            result = _deploy_node(ip, user, password, name, service_list, **cluster_data)
            if result["result"] == "failure":
                logging.error(
                    "Failed to deploy calico cni plugin on node: {0}. Please try deploying it manually.".format(node))

            break

    _sum_results(results)

    return results


def delete_host(host_name):
    """
    Delete a node in cluster

    1. check if host is a node in cluster
    2. delete node in k8s cluster
    3. reset host deployment

    :param host_name:
    :return:
    """
