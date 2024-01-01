pip freeze > requirements.txt
docker build -t chargecontrol -f Dockerfile .
docker tag chargecontrol:latest docker.diskstation/chargecontrol
docker push docker.diskstation/chargecontrol:latest