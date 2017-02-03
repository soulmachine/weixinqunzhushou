# weixinqunzhushou
微信群助手机器人

## 部署

确保 mongodb 能够连接得上，在Docker里`localhost`和`127.0.0.1`指向的就是Docker容器本身，因此不能用了，要直接用 MongoDB的IP地址。

运行，

    python3 main.py --host <mongodb_ip> --port <mongodb_port>

通过Docker运行，

    docker run -it --rm -v $(pwd):/code/wxqzs -w /code/wxqzs soulmachine/itchat python3 main.py --host 0.tcp.ngrok.io --port 16960
