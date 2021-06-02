# alfa

## Локальный старт

Требуется предварительная установка

* python
* docker
* virtualenv

```bash
rm -rf env || true
python3.9 -m venv env
source env/bin/activate
make sync-requirements
make run-server
```
