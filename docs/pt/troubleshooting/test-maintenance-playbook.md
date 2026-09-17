# Test Maintenance Playbook

Manutenção e melhoria contínua de testes.

## Estrutura de Testes

```
tests/
├── unit/           # Testes unitários
├── integration/    # Testes de integração
├── e2e/           # Testes end-to-end
├── fixtures/      # Dados de teste
└── conftest.py    # Configuração pytest
```

## Executar Testes

```bash
# Todos
pytest

# Unit apenas
pytest tests/unit -v

# Específico
pytest tests/unit/test_search.py::test_search_basic -v

# Com cobertura
pytest --cov=app --cov-report=html
```

## Mantendo Testes

### Adicionar Novo Teste

```python
# tests/unit/test_feature.py
import pytest

@pytest.fixture
def sample_image(db):
    """Criar imagem de teste"""
    return Image.create(filename="test.jpg")

def test_feature_basic(sample_image):
    """Testar funcionalidade básica"""
    result = do_something(sample_image)
    assert result is not None

def test_feature_edge_case():
    """Testar caso extremo"""
    with pytest.raises(ValueError):
        do_something(invalid_input)
```

### Atualizar Teste Obsoleto

Se teste falha após mudança de código:

1. Verificar se código está correto
2. Se sim, atualizar teste:

```python
# Antigo
def test_old():
    assert search("tag") == [1, 2, 3]

# Novo
def test_updated():
    assert search("tag") == [1, 2, 3, 4]  # adicionado novo resultado
```

### Remover Teste Redundante

Se dois testes fazem o mesmo:

- Manter o mais legível
- Remover o outro

## CI/CD Pipeline

GitHub Actions verifica:

1. **Lint**: `flake8`, `black`
2. **Type**: `mypy`
3. **Tests**: `pytest`
4. **Coverage**: Mínimo 80%

Arquivo: `.github/workflows/tests.yml`

## Problemas Comuns

### "Flaky Test" (Teste Intermitente)

Passa às vezes, falha outras:

```python
# Problema: Race condition
def test_async_feature():
    start_async_task()
    assert result == expected  # Race!

# Solução: Aguardar
def test_async_feature():
    start_async_task()
    wait_for_condition(lambda: task_done)
    assert result == expected
```

### Slow Test

Teste leva muito tempo:

```python
@pytest.mark.slow
def test_slow_operation():
    """Este teste é lento, pule em CI"""
    # ...

# Executar: pytest -m "not slow"
```

### Fluke Failures

Teste falha aleatoriamente:

- Aumentar timeout
- Usar retry (`pytest-retry`)
- Investigar logs

## Melhores Práticas

1. **Teste um comportamento por teste**
2. **Use fixtures para dados comuns**
3. **Mock externos (APIs, DB)**
4. **Nomeie testes descritivamente**
5. **Mantenha testes DRY**

## Cobertura

Ver cobertura:

```bash
pytest --cov=app --cov-report=html
open htmlcov/index.html
```

Metas:
- Unit: 90%+
- Integration: 70%+
- E2E: 50%+ (mais recursos)

## Debugging Testes

```bash
# Modo verbose
pytest -vv

# Parar no primeiro erro
pytest -x

# Debugger pdb
pytest --pdb

# Mostrar saída print
pytest -s
```

## Automação

```bash
# Watch mode (re-executar ao salvar)
pytest-watch

# Contínuo (CI/CD)
# GitHub Actions roda ao push
```

