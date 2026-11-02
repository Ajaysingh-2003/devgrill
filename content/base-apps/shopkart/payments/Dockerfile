# The payment provider ShopKart charges orders through: someone else's service, outside the
# player's repos. Standard library only.
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /srv/payments
COPY gateway.py ./
EXPOSE 8080 8081
CMD ["python", "gateway.py"]
