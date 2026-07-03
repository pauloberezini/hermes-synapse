import docker
import sys

client = docker.from_env()
code_str = 'print("Hello from Python container!")'
try:
    container = client.containers.run(
        image="python:3.11-slim",
        command=["python", "-c", code_str],
        detach=True,
        network_disabled=True,
        mem_limit="128m"
    )
    res = container.wait(timeout=10.0)
    print("res:", res)
    print("stdout:", container.logs(stdout=True, stderr=False).decode('utf-8'))
except Exception as e:
    print("Error:", e)
