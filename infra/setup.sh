# #!/usr/bin/env bash
# # =============================================================
# # setup.sh - Dựng hạ tầng PlayMood cho 4 máy ảo (Ubuntu 22.04)
# #
# # Cách dùng (chạy trên từng máy, cùng thư mục có file .env):
# #   sudo ./setup.sh vm3     # PostgreSQL 15 + Redis 7   (làm đầu tiên)
# #   sudo ./setup.sh vm4     # Kafka KRaft
# #   sudo ./setup.sh vm1     # K3s + Ingress
# #   sudo ./setup.sh vm2     # Recommender
# #
# # Chạy lại nhiều lần được (idempotent).
# # =============================================================
# set -euo pipefail

# ROLE="${1:-}"
# DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# export DEBIAN_FRONTEND=noninteractive

# log()  { echo -e "\n\033[1;32m==> $*\033[0m"; }
# warn() { echo -e "\033[1;33m[!] $*\033[0m"; }
# die()  { echo -e "\033[1;31m[x] $*\033[0m" >&2; exit 1; }

# # ---------- Kiểm tra đầu vào ----------
# [[ $EUID -eq 0 ]] || die "Chạy bằng sudo:  sudo ./setup.sh vm1|vm2|vm3|vm4"
# [[ -f "$DIR/.env" ]] || die "Thiếu file .env (cp .env.example .env rồi sửa)"
# set -a; source "$DIR/.env"; set +a

# for v in NET_IFACE NET_PREFIX GATEWAY DNS1 DNS2 VM1_IP VM2_IP VM3_IP VM4_IP \
#          PLAYMOOD_DB_NAME PLAYMOOD_DB_USER PLAYMOOD_DB_PASSWORD \
#          RECSYS_DB_NAME RECSYS_DB_USER RECSYS_DB_PASSWORD \
#          REDIS_PASSWORD KAFKA_VERSION KAFKA_TOPICS KAFKA_PARTITIONS; do
#   [[ -n "${!v:-}" ]] || die "Thiếu biến $v trong .env"
# done

# case "$ROLE" in
#   vm1) MY_IP="$VM1_IP"; HOST="playmood-vm1" ;;
#   vm2) MY_IP="$VM2_IP"; HOST="playmood-vm2" ;;
#   vm3) MY_IP="$VM3_IP"; HOST="playmood-vm3" ;;
#   vm4) MY_IP="$VM4_IP"; HOST="playmood-vm4" ;;
#   *)   die "Dùng:  sudo ./setup.sh vm1|vm2|vm3|vm4" ;;
# esac
# REAL_USER="${SUDO_USER:-root}"

# # =============================================================
# # PHẦN CHUNG CHO CẢ 4 MÁY
# # =============================================================
# common_setup() {
#   log "[$ROLE] Cập nhật hệ thống + cài gói cơ bản"
#   apt-get update -y
#   apt-get upgrade -y
#   apt-get install -y curl wget gnupg lsb-release ca-certificates \
#     ufw git vim htop net-tools chrony

#   log "[$ROLE] Đặt hostname = $HOST"
#   hostnamectl set-hostname "$HOST"

#   log "[$ROLE] Cập nhật /etc/hosts"
#   sed -i '/# BEGIN playmood/,/# END playmood/d' /etc/hosts
#   cat >> /etc/hosts <<EOF
# # BEGIN playmood
# $VM1_IP playmood-vm1 k3s
# $VM2_IP playmood-vm2 recsys
# $VM3_IP playmood-vm3 db
# $VM4_IP playmood-vm4 kafka
# # END playmood
# EOF

#   if [[ "${SET_STATIC_IP:-no}" == "yes" ]]; then
#     set_static_ip
#   else
#     warn "Bỏ qua đặt IP tĩnh (SET_STATIC_IP != yes). Nhớ tự đặt IP $MY_IP"
#   fi

#   log "[$ROLE] Firewall: mặc định chặn vào, mở SSH"
#   ufw --force reset >/dev/null
#   ufw default deny incoming
#   ufw default allow outgoing
#   ufw allow 22/tcp
# }

# set_static_ip() {
#   log "[$ROLE] Đặt IP tĩnh $MY_IP/$NET_PREFIX trên $NET_IFACE"
#   ip link show "$NET_IFACE" >/dev/null 2>&1 \
#     || die "Không thấy card mạng $NET_IFACE. Chạy 'ip a' rồi sửa NET_IFACE trong .env"

#   cat > /etc/netplan/99-playmood-static.yaml <<EOF
# network:
#   version: 2
#   ethernets:
#     $NET_IFACE:
#       dhcp4: false
#       addresses: [$MY_IP/$NET_PREFIX]
#       routes:
#         - to: default
#           via: $GATEWAY
#       nameservers:
#         addresses: [$DNS1, $DNS2]
# EOF
#   chmod 600 /etc/netplan/99-playmood-static.yaml
#   netplan generate
#   warn "netplan apply có thể làm rớt SSH nếu IP đổi. Nếu rớt, SSH lại bằng $MY_IP"
#   netplan apply || warn "netplan apply lỗi, kiểm tra lại file 99-playmood-static.yaml"
# }

# # =============================================================
# # VM3: PostgreSQL 15 + Redis 7
# # =============================================================
# setup_vm3() {
#   log "[vm3] Cài PostgreSQL 15 (repo PGDG)"
#   apt-get install -y postgresql-common
#   /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
#   apt-get install -y postgresql-15

#   log "[vm3] Cấu hình PostgreSQL cho phép kết nối từ vm1, vm2"
#   PGCONF=/etc/postgresql/15/main
#   mkdir -p "$PGCONF/conf.d"
#   cat > "$PGCONF/conf.d/99-playmood.conf" <<EOF
# listen_addresses = 'localhost,$VM3_IP'
# password_encryption = 'scram-sha-256'
# EOF

#   sed -i '/# BEGIN playmood/,/# END playmood/d' "$PGCONF/pg_hba.conf"
#   cat >> "$PGCONF/pg_hba.conf" <<EOF
# # BEGIN playmood
# host  $PLAYMOOD_DB_NAME  $PLAYMOOD_DB_USER  $VM1_IP/32  scram-sha-256
# host  $RECSYS_DB_NAME    $RECSYS_DB_USER    $VM2_IP/32  scram-sha-256
# # END playmood
# EOF
#   systemctl restart postgresql

#   log "[vm3] Tạo user + database"
#   sudo -u postgres psql -v ON_ERROR_STOP=1 \
#     -v pm_user="$PLAYMOOD_DB_USER" -v pm_pw="$PLAYMOOD_DB_PASSWORD" -v pm_db="$PLAYMOOD_DB_NAME" \
#     -v rs_user="$RECSYS_DB_USER"   -v rs_pw="$RECSYS_DB_PASSWORD"   -v rs_db="$RECSYS_DB_NAME" <<'SQL'
# SELECT format('CREATE ROLE %I LOGIN', :'pm_user')
#   WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'pm_user') \gexec
# SELECT format('CREATE ROLE %I LOGIN', :'rs_user')
#   WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'rs_user') \gexec

# ALTER ROLE :"pm_user" PASSWORD :'pm_pw';
# ALTER ROLE :"rs_user" PASSWORD :'rs_pw';

# SELECT format('CREATE DATABASE %I OWNER %I', :'pm_db', :'pm_user')
#   WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'pm_db') \gexec
# SELECT format('CREATE DATABASE %I OWNER %I', :'rs_db', :'rs_user')
#   WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'rs_db') \gexec
# SQL

#   log "[vm3] Cài Redis 7 (repo chính thức của Redis)"
#   curl -fsSL https://packages.redis.io/gpg | gpg --dearmor --yes -o /usr/share/keyrings/redis-archive-keyring.gpg
#   echo "deb [signed-by=/usr/share/keyrings/redis-archive-keyring.gpg] https://packages.redis.io/deb $(lsb_release -cs) main" \
#     > /etc/apt/sources.list.d/redis.list
#   apt-get update -y
#   # Ghim Redis 7.4 (repo mặc định sẽ cài bản mới nhất 8.x). Không có 7.4 thì dùng bản mới nhất.
#   apt-get install -y redis-server=6:7.4.* redis-tools=6:7.4.* \
#     || { warn "Không tìm thấy Redis 7.4, cài bản mới nhất"; apt-get install -y redis-server redis-tools; }

#   RCONF=/etc/redis/redis.conf
#   [[ -f "$RCONF.orig" ]] || cp "$RCONF" "$RCONF.orig"
#   sed -i -E "s/^bind .*/bind 127.0.0.1 $VM3_IP/" "$RCONF"
#   grep -v '^requirepass ' "$RCONF" > /tmp/redis.conf.new
#   cat /tmp/redis.conf.new > "$RCONF"
#   rm -f /tmp/redis.conf.new
#   grep -v -E '^(maxmemory|maxmemory-policy) ' "$RCONF" > /tmp/redis.conf.new
#   cat /tmp/redis.conf.new > "$RCONF"; rm -f /tmp/redis.conf.new
#   {
#     echo "requirepass $REDIS_PASSWORD"
#     echo "maxmemory 512mb"
#     echo "maxmemory-policy volatile-lru"
#   } >> "$RCONF"
#   systemctl enable redis-server
#   systemctl restart redis-server

#   log "[vm3] Firewall: chỉ cho vm1/vm2 vào DB, vm1 vào Redis"
#   ufw allow from "$VM1_IP" to any port 5432 proto tcp
#   ufw allow from "$VM2_IP" to any port 5432 proto tcp
#   ufw allow from "$VM1_IP" to any port 6379 proto tcp
# }

# # =============================================================
# # VM4: Kafka 1 broker, KRaft, cổng 9092
# # =============================================================
# setup_vm4() {
#   log "[vm4] Cài Java 17"
#   apt-get install -y openjdk-17-jre-headless

#   KDIR=/opt/kafka
#   KDATA=/var/lib/kafka/data
#   id kafka >/dev/null 2>&1 || useradd -r -m -d /var/lib/kafka -s /usr/sbin/nologin kafka

#   if [[ ! -x "$KDIR/bin/kafka-server-start.sh" ]]; then
#     log "[vm4] Tải Kafka $KAFKA_VERSION"
#     cd /tmp
#     wget -q --show-progress "https://archive.apache.org/dist/kafka/${KAFKA_VERSION}/kafka_2.13-${KAFKA_VERSION}.tgz"
#     mkdir -p "$KDIR"
#     tar -xzf "kafka_2.13-${KAFKA_VERSION}.tgz" -C "$KDIR" --strip-components=1
#     rm -f "kafka_2.13-${KAFKA_VERSION}.tgz"
#   fi

#   log "[vm4] Ghi cấu hình KRaft (advertised = $VM4_IP:9092)"
#   mkdir -p "$KDATA"
#   cat > "$KDIR/config/playmood-server.properties" <<EOF
# process.roles=broker,controller
# node.id=1
# controller.quorum.voters=1@127.0.0.1:9093
# listeners=PLAINTEXT://0.0.0.0:9092,CONTROLLER://127.0.0.1:9093
# advertised.listeners=PLAINTEXT://$VM4_IP:9092
# controller.listener.names=CONTROLLER
# inter.broker.listener.name=PLAINTEXT
# listener.security.protocol.map=CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
# log.dirs=$KDATA
# num.partitions=$KAFKA_PARTITIONS
# offsets.topic.replication.factor=1
# transaction.state.log.replication.factor=1
# transaction.state.log.min.isr=1
# auto.create.topics.enable=true
# log.retention.hours=168
# EOF

#   if [[ ! -f "$KDATA/meta.properties" ]]; then
#     log "[vm4] Format storage KRaft (chỉ làm lần đầu)"
#     CID="$("$KDIR/bin/kafka-storage.sh" random-uuid)"
#     "$KDIR/bin/kafka-storage.sh" format -t "$CID" -c "$KDIR/config/playmood-server.properties"
#   fi
#   chown -R kafka:kafka "$KDIR" /var/lib/kafka

#   log "[vm4] Tạo service systemd"
#   cat > /etc/systemd/system/kafka.service <<EOF
# [Unit]
# Description=Apache Kafka (KRaft)
# After=network.target

# [Service]
# User=kafka
# Environment="KAFKA_HEAP_OPTS=-Xms512m -Xmx512m"
# ExecStart=$KDIR/bin/kafka-server-start.sh $KDIR/config/playmood-server.properties
# ExecStop=$KDIR/bin/kafka-server-stop.sh
# Restart=on-failure
# LimitNOFILE=100000

# [Install]
# WantedBy=multi-user.target
# EOF
#   systemctl daemon-reload
#   systemctl enable kafka
#   systemctl restart kafka

#   log "[vm4] Đợi broker lên rồi tạo topic"
#   for i in $(seq 1 30); do
#     "$KDIR/bin/kafka-topics.sh" --bootstrap-server "$VM4_IP:9092" --list >/dev/null 2>&1 && break
#     sleep 2
#     [[ $i -eq 30 ]] && die "Kafka không lên. Xem: journalctl -u kafka -n 50"
#   done
#   for t in $KAFKA_TOPICS; do
#     "$KDIR/bin/kafka-topics.sh" --bootstrap-server "$VM4_IP:9092" \
#       --create --if-not-exists --topic "$t" \
#       --partitions "$KAFKA_PARTITIONS" --replication-factor 1
#   done

#   log "[vm4] Firewall: chỉ cho vm1, vm2 vào cổng 9092"
#   ufw allow from "$VM1_IP" to any port 9092 proto tcp
#   ufw allow from "$VM2_IP" to any port 9092 proto tcp
# }

# # =============================================================
# # VM1: K3s + Ingress (Traefik có sẵn trong K3s)
# # =============================================================
# setup_vm1() {
#   if ! command -v k3s >/dev/null 2>&1; then
#     log "[vm1] Cài K3s"
#     curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--write-kubeconfig-mode 644 --tls-san $VM1_IP" sh -
#   else
#     log "[vm1] K3s đã có, bỏ qua"
#   fi

#   log "[vm1] Đợi node Ready"
#   for i in $(seq 1 30); do
#     k3s kubectl get nodes 2>/dev/null | grep -q ' Ready' && break
#     sleep 4
#   done
#   k3s kubectl wait --for=condition=Ready node --all --timeout=120s

#   if [[ "$REAL_USER" != "root" ]]; then
#     UHOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
#     mkdir -p "$UHOME/.kube"
#     cp /etc/rancher/k3s/k3s.yaml "$UHOME/.kube/config"
#     chown -R "$REAL_USER":"$REAL_USER" "$UHOME/.kube"
#     grep -q 'KUBECONFIG' "$UHOME/.bashrc" || echo 'export KUBECONFIG=$HOME/.kube/config' >> "$UHOME/.bashrc"
#   fi

#   log "[vm1] Firewall: 80 (Cloudflare), 443, 6443 (kubectl), cho pod/service CIDR của K3s"
#   ufw allow 80/tcp
#   ufw allow 443/tcp
#   ufw allow 6443/tcp
#   ufw allow from 10.42.0.0/16
#   ufw allow from 10.43.0.0/16
#   ufw default allow routed
# }

# # =============================================================
# # VM2: Recommender (Python)
# # =============================================================
# setup_vm2() {
#   log "[vm2] Cài Python + công cụ build"
#   apt-get install -y python3 python3-venv python3-pip python3-dev build-essential libpq-dev

#   APP=/opt/recommender
#   mkdir -p "$APP"
#   [[ -d "$APP/venv" ]] || python3 -m venv "$APP/venv"
#   chown -R "$REAL_USER":"$REAL_USER" "$APP"
#   # Máy 2 chỉ nhận SSH; nó tự kết nối ra Kafka (vm4) và PostgreSQL (vm3)
# }

# # =============================================================
# # CHẠY
# # =============================================================
# common_setup
# case "$ROLE" in
#   vm1) setup_vm1 ;;
#   vm2) setup_vm2 ;;
#   vm3) setup_vm3 ;;
#   vm4) setup_vm4 ;;
# esac

# ufw --force enable
# log "[$ROLE] XONG. Kiểm tra nhanh:"
# case "$ROLE" in
#   vm1) echo "  kubectl get nodes ; kubectl get pods -A" ;;
#   vm2) echo "  nc -zv $VM4_IP 9092 ; nc -zv $VM3_IP 5432" ;;
#   vm3) echo "  sudo -u postgres psql -c '\\l' ; redis-cli -a '\$REDIS_PASSWORD' ping" ;;
#   vm4) echo "  /opt/kafka/bin/kafka-topics.sh --bootstrap-server $VM4_IP:9092 --list" ;;
# esac