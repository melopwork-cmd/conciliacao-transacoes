# Conciliação de Transações

Ferramenta de linha de comando em Python para comparar um registro interno com um arquivo de liquidação. O relatório aponta correspondências, diferenças de valor ou moeda, referências duplicadas e registros que aparecem em apenas um dos arquivos.

## Executar

Python 3.12. A aplicação usa a biblioteca padrão e SQLite.

~~~text
python -m conciliacao --db exemplo.db reconcile examples/ledger.csv examples/settlements.csv
python -m unittest discover -s tests -v
~~~

O exemplo devolve seis referências e exercita todas as classificações. Copie o batch_id da saída para recuperar o mesmo relatório posteriormente.

~~~text
python -m conciliacao --db exemplo.db report BATCH_ID
~~~

Para revisar somente as divergências em uma planilha, exporte o lote salvo em CSV.

~~~text
python -m conciliacao --db exemplo.db report BATCH_ID --format csv
~~~

O CSV usa ponto e vírgula, informa as contagens por origem e mantém os valores em centavos. Quando há mais de um registro na mesma origem, o valor correspondente fica em branco para evitar uma escolha arbitrária.

## Formato

~~~csv
referencia;valor;moeda
PED-1001;99,90;BRL
~~~

Use UTF-8 e ponto e vírgula. Os valores positivos aceitam vírgula ou ponto decimal com até duas casas. A comparação usa centavos inteiros e exige a mesma moeda. Referências duplicadas são sinalizadas com os números de linha originais para revisão.

O identificador do lote é derivado do conteúdo dos dois arquivos em ordem. O SQLite usa esse identificador como chave primária para que reimportações do mesmo par gerem um único registro. O relatório não agrega valores entre moedas.

## English

A local Python reconciliation CLI with exact currency amounts, row-level discrepancy reporting, and idempotent SQLite storage. The example files are synthetic. Independent portfolio project built with AI assistance.

- [Python sqlite3](https://docs.python.org/3/library/sqlite3.html)

### Verificação em automações

Use `reconcile --fail-on-discrepancies` para retornar código 1 quando houver divergências. O relatório continua disponível no SQLite e na saída padrão.

### Histórico de lotes

Execute `python -m conciliacao batches --limit 10` para listar os últimos lotes importados. Use o `batch_id` com o comando `report`.

Use `report BATCH_ID --format summary` para obter apenas o identificador do lote e as contagens de referências e divergências.

Use `reconcile --dry-run` para exibir o relatório sem salvar o lote no banco.
