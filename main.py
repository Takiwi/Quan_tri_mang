import subprocess

result = subprocess.run(
    ["ssh", "tanhoang@192.168.120.130", "echo Hello from service && hostname"],
    capture_output=True,
    text=True,
)
print(result.stdout)
print("loi:", result.stderr)
