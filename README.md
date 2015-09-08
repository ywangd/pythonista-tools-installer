# Pythonista Tools Installer

A front-end UI program to browse and/or download scripts listed on 
[Pythonista-Tools](https://github.com/Pythonista-Tools/Pythonista-Tools).
To install, copy and run following one-line python statements in Pythonista
interactive prompt.

```python
import requests as r; o=open('ptinstaller.py','w'); o.write(r.get('http://j.mp/pt-i').text); o.close()
```

The scripts are by default installed under **`~/Documents/bin/`**.