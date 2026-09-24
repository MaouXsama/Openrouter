after terraform apply
see the new azure_storage_account_name
azure_storage_container_name
postgresql_server_host
public_ip_address

then go to the see the new azure_storage_account_name
in sas [ shared access signature]
apply all the allowed resource types 
and extend the expiry time and generate the sas and connection string

copy the new blob service sas url
update the url in the .env

after connecting to the new vm 

ssh azureuser@   IP

mkdir -p ~/Openrouter

make sure ur in the right path C:\Users\yazee\Desktop\Cloud Computing - SDA\Openrouter).

scp -r * azureuser@13.72.72.218:~/Openrouter/

scp .env .dockerignore azureuser@13.72.72.218:~/Openrouter/


# 1. تنظيف أي مسارات قديمة مشوهة لتفادي أخطاء الـ apt update
sudo rm -f /etc/apt/sources.list.d/docker.list

# 2. تحديث قائمة الحزم الأساسية للنظام
sudo apt-get update

# 3. تثبيت Docker ومحرك الـ Compose الرسمي المدمج في نظام Ubuntu دفعة واحدة
sudo apt-get install -y docker.io docker-compose-v2

sudo docker compose up -d --build
