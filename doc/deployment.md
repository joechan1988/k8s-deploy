# 沃云容器平台后端部署手册

## 准备工作

- 文件清单  

  - 镜像包文件(<安装目录>/images/)
  
  |文件名 | 描述 |
  |------|------|
  | kde.tar | 部署程序镜像|
  |pod-infra.tar|Pod基础镜像|
  |kube-dns.tar|kube-dns组件镜像|
  |calico.tar|calico组件镜像|
  |traefik.tar|Traefik组件镜像|

  - Docker安装文件(<安装目录>/docker-installation/)

  |文件名 | 描述 |
  |------|------|
  |docker.tar|Docker引擎安装文件及依赖包|
  |docker-compose | docker-compose程序文件|


  - Harbor镜像仓库安装包(<安装目录>/harbor/)

  |文件名 | 描述 |
  |------|------|
  |harbor.tar|Harbor镜像仓库安装文件|

  
  - 文档(<安装目录>/doc/)
  
  |文件名 | 描述 |
  |------|------|
  |deployment.md|部署文档|
  |configuration.md|配置说明文档|
  |cluster.yml|配置文件模板|
     
  -  可执行程序文件(默认已包含在kde.tar中)
  
  |文件名 | 描述 |
  |------|------|
  | kube-apiserver | API Server 程序文件|
  |kube-controller-manager| Controller Manager 程序文件|
  |kube-scheduler| Scheduler 程序文件|
  |kube-proxy| Proxy 程序文件|
  |kubelet| Kubelet 程序文件|
  |etcd| Etcd 程序文件|
  |etcdctl| Etcd 命令行程序|
  |cfssl| 证书工具|
  

- 操作系统
  - 版本： CentOS 7, kernel 3.10
  - 必备组件：
    - jq
    - conntrack
    - socat
    - bind-utils

- 配置文件说明  

  详见configuration.md

## 部署操作
### kubernetes集群部署

###### 前置操作
1. 检查必备组件是否安装
2. 根据配置文件说明，生成并检查配置文件`/etc/kde/cluster.yml`
3. 载入所有镜像文件

    执行
    ```
    docker load -i <安装目录>/images/<文件名>.tar
    ```
   
4. Docker引擎部署

    - 说明： 需要在所有主机节点（包含部署所在主机）部署docker引擎

    - 准备yum源

    - 使用现存yum源：解包 `<安装目录>/docker-installation/docker.tar`,将文件夹中所有rpm包加入已有yum源中
    - 使用本地yum源：解包 `<安装目录>/docker-installation/docker.tar`,复制文件夹内docker.repo文件到/etc/yum.repos.d/,
        修改file指向的路径,并执行
        ```
        yum makecache
        ```

    - 执行安装操作
        ```
        yum install -y docker-1.12.6
        ```

    - 安装docker-compose客户端
        ```
        cp <安装目录>/docker-installation/docker-compose /usr/bin/
        chmod +x /usr/bin/docker-compose
        ```

###### k8s集群部署操作

  - 初始化部署  
    
    执行以下命令：
    ```
    docker run \
         -t -i --net=host --rm \
         -v /var/run/docker.sock:/var/run/docker.sock:ro \
         -v /etc/kde:/etc/kde \
         -v /etc/localtime:/etc/localtime:ro \
         kde \
         kde deploy

    docker run -t -i --net=host \
        --rm -v /var/run/docker.sock:/var/run/docker.sock:ro \
        -v /etc/kde:/etc/kde \
        -v /etc/localtime:/etc/localtime:ro \
        kde kubectl \
        --kubeconfig=/etc/kde/auth/admin.kubeconfig apply -f \
        /etc/kde/addons/DNS/

    docker run -t -i --net=host --rm \
        -v /var/run/docker.sock:/var/run/docker.sock:ro \
        -v /etc/kde:/etc/kde \
        -v /etc/localtime:/etc/localtime:ro \
        kde kubectl --kubeconfig=/etc/kde/auth/admin.kubeconfig \
        apply -f /etc/kde/addons/traefik/
    ```

  - 如部署出现问题，可进行部署重置（清除）

    执行以下命令：
    ```
    docker run \
             -t -i --net=host --rm \
             -v /var/run/docker.sock:/var/run/docker.sock:ro \
             -v /etc/kde:/etc/kde \
             -v /etc/localtime:/etc/localtime:ro \
             kde \
             kde reset
    ```
    
### Harbor镜像仓库部署

1. 将harbor.tar文件解包,进入解包目录
2. 载入harbor镜像  

    执行以下命令(文件名中版本可能需要替换)
    ```
    docker load -i harbor.v1.4.0.tar.gz
    ```
    
3. 修改配置文件harbor.cfg

  - hostname: 修改为本机对外IP
  - harbor_admin_password: 管理界面登陆、镜像仓库密码
    
4. 执行部署操作

    ```
    ./prepare
    docker-compose up -d
    ```
