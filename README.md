# Dashboard for DHCP/DNS on Raspberry PI

I have created this python file to run a dhcp/dns server on raspberry with dnsmasq.
This is for testing network related things.


## Added API function
### List, add and remove devices!
<p>To list all hosts by API:curl http://your-ip:8080/api/hosts</p><br>
<p>To add a host by API: curl -X POST -H "Content-Type: application/json" -d "{\"mac\":\"00:11:22:33:44:55\",\"hostname\":\"newdevice\",\"ip\":\"your-ip\"}" http://your-ip:8080/api/hosts</p><br>
<p>To delete a host by API: curl -X DELETE http://your-ip:8080/api/hosts/00:11:22:33:44:55  ==> MAC Address to delete </p><br>

### View log file by API!
<p>View 10 last lines from log: curl http://your-ip:8080/api/logs?lines=10</p><br>
<p>View all lines from logfile: curl http://your-ip:8080/api/logs</p>


### Postman
<p>It is also possible to use other software like Postman to use the API for viewing devices or logfile.</p>
