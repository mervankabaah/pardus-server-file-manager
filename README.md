# Pardus Sunucu File Manager

Bu proje, Pardus Sunucu üzerinde `/var/www/html` dizinini web arayüzünden yönetmek için hazırlanmış basit bir Flask tabanlı dosya yöneticisidir.

Uygulama ile dosya ve klasör listeleme, yükleme, indirme, yeniden adlandırma, silme, kopyalama, kesme, yapıştırma, zip oluşturma ve zip çıkarma işlemleri yapılabilir.

## Özellikler

- Kullanıcı adı ve şifre ile giriş
- 5 hatalı girişten sonra tarayıcı bazlı 5 saat engelleme
- Dosya ve klasör yükleme
- Sürükle-bırak ile yükleme
- Dosya indirme
- Yeni klasör oluşturma
- Dosya veya klasör yeniden adlandırma
- Tekli ve çoklu silme
- Tekli ve çoklu kopyalama, kesme, yapıştırma
- Tekli ve çoklu zip oluşturma
- Zip dosyalarını çıkarma
- Dizin dışına çıkmayı engelleyen güvenli yol kontrolü

## Sistem Gereksinimleri

- Pardus Sunucu
- Python 3
- Python sanal ortam desteği
- Nginx
- systemd
- Alan adı kullanacaksanız DNS yönetim erişimi

## Proje Yapısı

```text
.
├── app.py
└── README.md
```

Uygulama varsayılan olarak şu dizini yönetir:

```python
BASE_DIR = '/var/www/html'
```

Varsayılan giriş bilgileri:

```python
USERNAME = 'admin'
PASSWORD = 'admin'
```

Kurulumdan önce bu değerleri mutlaka değiştirmeniz önerilir.

## 1. Sunucu Paketlerini Kurma

Sunucuya SSH ile bağlanın:

```bash
ssh kullanici@SUNUCU_IP_ADRESI
```

Paketleri güncelleyin:

```bash
sudo apt update
sudo apt upgrade -y
```

Gerekli paketleri kurun:

```bash
sudo apt install -y python3 python3-venv python3-pip nginx
```

SSL sertifikası kullanacaksanız Certbot paketlerini de kurun:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

## 2. Projeyi Sunucuya Kopyalama

Uygulamayı örnek olarak `/opt/pardus-filemanager` dizinine kuracağız.

```bash
sudo mkdir -p /opt/pardus-filemanager
sudo chown -R $USER:$USER /opt/pardus-filemanager
```

Dosyaları sunucuya kopyalayın. Kendi bilgisayarınızdan örnek:

```bash
scp app.py README.md kullanici@SUNUCU_IP_ADRESI:/opt/pardus-filemanager/
```

Sunucuda proje dizinine geçin:

```bash
cd /opt/pardus-filemanager
```

## 3. Kullanıcı Adı, Şifre ve Gizli Anahtarı Değiştirme

`app.py` dosyasını açın:

```bash
nano app.py
```

Aşağıdaki alanları değiştirin:

```python
app.secret_key = 'cok_guvenli_gizli_anahtar_degistirilebilir'
BASE_DIR = '/var/www/html'
USERNAME = 'admin'
PASSWORD = 'admin'
```

Örnek:

```python
app.secret_key = 'uzun-rastgele-bir-secret-key-yazin'
BASE_DIR = '/var/www/html'
USERNAME = 'siteyonetici'
PASSWORD = 'guclu-bir-sifre'
```

`BASE_DIR`, uygulamanın yöneteceği ana klasördür. Web siteniz `/var/www/html` altında duruyorsa bu değer doğru kalabilir.

## 4. Python Sanal Ortamı Oluşturma

Proje dizininde sanal ortam oluşturun:

```bash
python3 -m venv venv
```

Sanal ortamı aktif edin:

```bash
source venv/bin/activate
```

Gerekli Python paketlerini kurun:

```bash
pip install --upgrade pip
pip install flask gunicorn werkzeug
```

Hızlı test:

```bash
python app.py
```

Uygulama varsayılan olarak sadece sunucu içinde şu adreste çalışır:

```text
http://127.0.0.1:5050
```

Testten sonra `CTRL+C` ile kapatın.

## 5. Yönetilecek Dizinin Yetkilerini Ayarlama

Uygulama `/var/www/html` içinde dosya oluşturacağı, sileceği ve değiştireceği için servis kullanıcısının bu dizinde yazma izni olmalıdır.

Önerilen yöntem, uygulama için ayrı bir sistem kullanıcısı oluşturmaktır:

```bash
sudo useradd --system --home /opt/pardus-filemanager --shell /usr/sbin/nologin filemanager
```

Proje dosyalarının sahibini ayarlayın:

```bash
sudo chown -R filemanager:filemanager /opt/pardus-filemanager
```

Yönetilecek web dizinini uygulama kullanıcısına yazılabilir yapın:

```bash
sudo chown -R filemanager:www-data /var/www/html
sudo find /var/www/html -type d -exec chmod 775 {} \;
sudo find /var/www/html -type f -exec chmod 664 {} \;
```

Bu yapılandırmada `filemanager` kullanıcısı dosyaları yönetir, `www-data` grubu ise Nginx'in dosyaları okuyabilmesini sağlar.

## 6. systemd Servisi Olarak Çalıştırma

Servis dosyası oluşturun:

```bash
sudo nano /etc/systemd/system/pardus-filemanager.service
```

Aşağıdaki içeriği ekleyin:

```ini
[Unit]
Description=Pardus Sunucu File Manager
After=network.target

[Service]
User=filemanager
Group=www-data
WorkingDirectory=/opt/pardus-filemanager
Environment="PATH=/opt/pardus-filemanager/venv/bin"
ExecStart=/opt/pardus-filemanager/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5050 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Servisi etkinleştirin ve başlatın:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pardus-filemanager
sudo systemctl start pardus-filemanager
```

Durum kontrolü:

```bash
sudo systemctl status pardus-filemanager
```

Logları izlemek için:

```bash
sudo journalctl -u pardus-filemanager -f
```

Servisi yeniden başlatmak için:

```bash
sudo systemctl restart pardus-filemanager
```

## 7. Nginx ile Domain Bağlama

Örnek domain:

```text
panel.example.com
```

DNS panelinizden şu kaydı ekleyin:

```text
Type: A
Name: panel
Value: SUNUCU_IP_ADRESI
TTL: Auto veya 300
```

Ana domain kullanacaksanız:

```text
Type: A
Name: @
Value: SUNUCU_IP_ADRESI
```

DNS yayılımı birkaç dakika ile birkaç saat arasında sürebilir.

Nginx site dosyası oluşturun:

```bash
sudo nano /etc/nginx/sites-available/pardus-filemanager
```

Aşağıdaki yapılandırmayı ekleyin. `server_name` kısmını kendi domaininizle değiştirin:

```nginx
server {
    listen 80;
    server_name panel.example.com;

    client_max_body_size 1000M;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }
}
```

Siteyi aktif edin:

```bash
sudo ln -s /etc/nginx/sites-available/pardus-filemanager /etc/nginx/sites-enabled/pardus-filemanager
```

Varsayılan Nginx sitesini kapatmak isterseniz:

```bash
sudo rm -f /etc/nginx/sites-enabled/default
```

Nginx yapılandırmasını test edin:

```bash
sudo nginx -t
```

Nginx'i yeniden yükleyin:

```bash
sudo systemctl reload nginx
```

Artık uygulamaya şu adresten erişebilirsiniz:

```text
http://panel.example.com
```

## 8. HTTPS SSL Sertifikası Alma

Domain DNS kaydı sunucu IP adresine doğru yönlenmiş olmalıdır.

Certbot ile SSL sertifikası alın:

```bash
sudo certbot --nginx -d panel.example.com
```

Certbot size HTTP'den HTTPS'e yönlendirme yapmak isteyip istemediğinizi sorabilir. Genellikle yönlendirme seçilmelidir.

Sertifika yenileme testi:

```bash
sudo certbot renew --dry-run
```

HTTPS sonrası erişim:

```text
https://panel.example.com
```

## 9. Güvenlik Önerileri

Kurulumdan sonra aşağıdaki adımları mutlaka uygulayın:

- `USERNAME` ve `PASSWORD` değerlerini değiştirin.
- `app.secret_key` değerini uzun ve rastgele bir değer yapın.
- Paneli herkese açık kullanacaksanız mutlaka HTTPS açın.
- Mümkünse panel domainini tahmin edilmesi zor bir subdomain üzerinde çalıştırın.
- Sunucuda güvenlik duvarı kullanın.
- Sadece `80` ve `443` portlarını dış dünyaya açın.
- Uygulama zaten `127.0.0.1:5050` üzerinde dinlediği için `5050` portunu dışarı açmayın.
- Düzenli yedek alın. Bu uygulama dosya silebildiği için hatalı işlemde veri kaybı olabilir.

UFW kullanıyorsanız:

```bash
sudo apt install -y ufw
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

## 10. Kullanım

Tarayıcıdan domaininize gidin:

```text
https://panel.example.com
```

Giriş ekranında `app.py` içinde belirlediğiniz kullanıcı adı ve şifreyi kullanın.

Ana ekranda `/var/www/html` içeriği listelenir.

Yapabilecekleriniz:

- Klasöre girmek için klasör adına tıklayın.
- Bir üst klasöre çıkmak için `Bir üst klasör...` bağlantısını kullanın.
- Dosya indirmek için indirme butonuna basın.
- Yeni klasör oluşturmak için `Yeni Klasör` butonunu kullanın.
- Dosya veya klasör yüklemek için `Yükle` butonunu açın.
- Dosya veya klasörleri sürükleyip yükleme alanına bırakın.
- Dosya seçmek için `Dosya Seç` butonunu kullanın.
- Klasör seçmek için `Klasör Seç` butonunu kullanın.
- Satıra tıklayarak öğe seçin.
- `CTRL` ile birden fazla öğe seçin.
- `SHIFT` ile aralık seçimi yapın.
- Seçili öğeleri üst menüden kopyalayın, kesin, silin, zipleyin veya zipten çıkarın.
- Tekli işlemler için her satırın sağındaki işlem butonlarını kullanın.

## 11. Güncelleme

Yeni `app.py` dosyasını sunucuya kopyalayın:

```bash
scp app.py kullanici@SUNUCU_IP_ADRESI:/opt/pardus-filemanager/app.py
```

Dosya sahibini düzeltin:

```bash
sudo chown filemanager:filemanager /opt/pardus-filemanager/app.py
```

Servisi yeniden başlatın:

```bash
sudo systemctl restart pardus-filemanager
```

Logları kontrol edin:

```bash
sudo journalctl -u pardus-filemanager -n 100 --no-pager
```

## 12. Sorun Giderme

Servis çalışıyor mu?

```bash
sudo systemctl status pardus-filemanager
```

Uygulama portu dinliyor mu?

```bash
sudo ss -ltnp | grep 5050
```

Nginx yapılandırması doğru mu?

```bash
sudo nginx -t
```

Nginx logları:

```bash
sudo tail -f /var/log/nginx/error.log
```

Uygulama logları:

```bash
sudo journalctl -u pardus-filemanager -f
```

Yetki hatası alırsanız:

```bash
sudo chown -R filemanager:www-data /var/www/html
sudo find /var/www/html -type d -exec chmod 775 {} \;
sudo find /var/www/html -type f -exec chmod 664 {} \;
sudo systemctl restart pardus-filemanager
```

502 Bad Gateway hatası alırsanız:

- `pardus-filemanager` servisi çalışmıyor olabilir.
- Gunicorn `127.0.0.1:5050` üzerinde dinlemiyor olabilir.
- Nginx `proxy_pass` adresi yanlış olabilir.

Kontrol:

```bash
sudo systemctl restart pardus-filemanager
sudo systemctl reload nginx
sudo journalctl -u pardus-filemanager -n 50 --no-pager
```

413 Request Entity Too Large hatası alırsanız:

- Nginx `client_max_body_size 1000M;` değeri eksik veya düşük olabilir.
- Flask tarafında `MAX_CONTENT_LENGTH` değeri 1 GB olarak ayarlıdır.

Nginx'i yeniden yükleyin:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 13. Kaldırma

Servisi durdurun ve devre dışı bırakın:

```bash
sudo systemctl stop pardus-filemanager
sudo systemctl disable pardus-filemanager
```

Servis dosyasını silin:

```bash
sudo rm -f /etc/systemd/system/pardus-filemanager.service
sudo systemctl daemon-reload
```

Nginx site dosyalarını kaldırın:

```bash
sudo rm -f /etc/nginx/sites-enabled/pardus-filemanager
sudo rm -f /etc/nginx/sites-available/pardus-filemanager
sudo nginx -t
sudo systemctl reload nginx
```

Proje dizinini kaldırın:

```bash
sudo rm -rf /opt/pardus-filemanager
```

Uygulama kullanıcısını kaldırmak isterseniz:

```bash
sudo userdel filemanager
```

> Not: `/var/www/html` içeriği kaldırma işlemi sırasında silinmez. Web dosyalarınızı ayrıca yedekleyin ve gerekiyorsa manuel yönetin.
