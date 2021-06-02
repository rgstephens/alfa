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


## Добавление в другой проект в виде зависимости
requirements.txt
```
git+ssh://git@github.com/magnit-tech/alfa.git
```
pyproject.toml
```
alfa = {git = "git@github.com:magnit-tech/alfa.git", rev = "master"}
```