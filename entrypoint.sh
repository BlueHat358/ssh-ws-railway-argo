#!/bin/bash

# Mengambil environment variables atau menggunakan nilai default
USER_NAME="${SSH_USER:-jatim}"
USER_PASS="${SSH_PASSWORD:-jatim}"

# Port PUBLIK (yang di-arahkan Railway TCP Proxy ke sini)
PUBLIC_PORT="${PORT:-8080}"

# Port INTERNAL, tidak diekspos keluar, hanya dipakai antar-proses di dalam container
SSL_INTERNAL_PORT="${SSL_INTERNAL_PORT:-2443}"
WS_INTERNAL_PORT="${WS_INTERNAL_PORT:-8880}"

echo "[*] Mengonfigurasi Server Message (Banner Pra-Login)..."
cat << 'EOF' > /etc/issue.net
<p style="text-align:center"><big><big><big><big><big><big><big><big><big><big><big>🌏</big></big></big></big></big></big></big></big></big></big></big></p>
EOF

echo "Banner /etc/issue.net" >> /etc/ssh/sshd_config
sed -i 's/PrintMotd no/PrintMotd yes/g' /etc/ssh/sshd_config
rm -f /etc/update-motd.d/*
cp /etc/issue.net /etc/motd

echo "[*] Mengonfigurasi Respon Server (Pasca-Login)..."
# Skrip ini akan dieksekusi otomatis ketika user berhasil login
cat << 'EOF' > /etc/profile.d/99-respon-server.sh
#!/bin/bash
clear
echo -e "\e[1;36m=================================================\e[0m"
echo -e "\e[1;32m       [✓] BERHASIL TERHUBUNG KE SERVER!         \e[0m"
echo -e "\e[1;36m=================================================\e[0m"
echo -e "\e[1;37m Username     : \e[1;33m$USER\e[0m"
echo -e "\e[1;37m Waktu Server : \e[1;33m$(date)\e[0m"
echo -e "\e[1;37m OS           : \e[1;33mUbuntu 22.04 LTS\e[0m"
echo -e "\e[1;36m=================================================\e[0m"
echo -e "\e[1;31m   TETAP PATUHI RULES SERVER AGAR TIDAK BANNED   \e[0m"
echo -e "\e[1;36m=================================================\e[0m"
EOF
chmod +x /etc/profile.d/99-respon-server.sh

echo "[*] Mengonfigurasi User SSH..."
if ! id "$USER_NAME" &>/dev/null; then
    useradd -m -s /bin/bash "$USER_NAME"
    usermod -aG sudo "$USER_NAME"
fi
echo "$USER_NAME:$USER_PASS" | chpasswd

echo "[*] Memulai OpenSSH Server di Port 22..."
/usr/sbin/sshd

echo "[*] Membuat konfigurasi Stunnel (internal) di Port $SSL_INTERNAL_PORT..."
cat <<EOF > /etc/stunnel/stunnel.conf
pid = /var/run/stunnel.pid
foreground = yes
debug = 4

[ssh-ssl]
accept = 127.0.0.1:$SSL_INTERNAL_PORT
connect = 127.0.0.1:22
cert = /etc/stunnel/stunnel.pem
EOF

echo "[*] Menambahkan sesuatu di .bashrc..."
cat <<'EOF'>> ~/.bashrc
clear
R='\e[1;31m'
G='\e[1;32m'
C='\e[1;36m'
N='\e[0m'

alias c='clear'
alias x='exit'
alias +x='chmod +x'
alias cls='clear;ls'

menu
EOF

echo "[*] Memulai Stunnel (internal, port $SSL_INTERNAL_PORT)..."
stunnel /etc/stunnel/stunnel.conf &

echo "[*] Memulai WebSocket Proxy (internal, port $WS_INTERNAL_PORT, forward ke SSH 127.0.0.1:22)..."
WS_PORT="$WS_INTERNAL_PORT" WS_TARGET_HOST="127.0.0.1" WS_TARGET_PORT="22" \
    python3 /usr/local/bin/ws-proxy.py &

# --- Argo Tunnel (cloudflared), jalur tambahan khusus WS ---
# Isi CF_TUNNEL_TOKEN di environment variable Railway untuk mengaktifkan.
# Di dashboard Cloudflare Zero Trust, arahkan Public Hostname tunnel ini
# ke service HTTP: localhost:$WS_INTERNAL_PORT (bukan port mux publik).
if [ -n "$CF_TUNNEL_TOKEN" ]; then
    echo "[*] Menjalankan Cloudflare Tunnel (Argo) via token..."
    cloudflared tunnel run --token "$CF_TUNNEL_TOKEN" &
else
    echo "[!] CF_TUNNEL_TOKEN tidak diset -> Cloudflare Tunnel dilewati."
fi

echo "[*] Memulai Multiplexer di Port PUBLIK $PUBLIC_PORT (auto-deteksi SSL vs WS)..."
exec env \
    PORT="$PUBLIC_PORT" \
    SSL_TARGET_HOST="127.0.0.1" SSL_TARGET_PORT="$SSL_INTERNAL_PORT" \
    WS_MUX_TARGET_HOST="127.0.0.1" WS_MUX_TARGET_PORT="$WS_INTERNAL_PORT" \
    python3 /usr/local/bin/mux.py
