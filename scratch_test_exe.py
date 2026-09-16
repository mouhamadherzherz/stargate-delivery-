import subprocess
import time

exe_path = r"D:\STARGATE\repo\dist\StargateDelivery.exe"
print("Launching:", exe_path)

p = subprocess.Popen([exe_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
time.sleep(4)

ret = p.poll()
if ret is not None:
    stdout, stderr = p.communicate()
    print("Process died! Exit code:", ret)
    print("STDOUT:", stdout)
    print("STDERR:", stderr)
else:
    print("Process is alive and running! PID:", p.pid)
    p.kill()
