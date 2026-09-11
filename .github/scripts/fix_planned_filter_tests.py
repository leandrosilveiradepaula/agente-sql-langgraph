from pathlib import Path

path = Path("testar_sql_generation.py")
text = path.read_text(encoding="utf-8")
old = '\n\nif __name__ == "__main__":\n    main()\n\n\n\ndef _plan_with_required_filter()'
new = '\n\ndef _plan_with_required_filter()'
if text.count(old) != 1:
    raise RuntimeError(f"expected one main anchor, got {text.count(old)}")
text = text.replace(old, new, 1)
footer = '''\n\nif __name__ == "__main__":\n    main()\n    extra_tests = [\n        ("required filter separado do binding", test_required_filter_e_binding_fisico_sao_separados),\n        ("required filter sem binding fail closed", test_required_filter_sem_binding_falha_fechada),\n        ("binding ambiguo fail closed", test_binding_ambiguo_falha_fechada),\n        ("filtros deterministicos", test_filtros_sao_deterministicos_e_ignoram_nao_referenciados),\n        ("planned filter sem campos fisicos", test_planned_filter_nao_aceita_campos_fisicos),\n    ]\n    for index, (name, test_function) in enumerate(extra_tests, start=44):\n        test_function()\n        print(f"TESTE {index} - {name}: OK")\n'''
if 'extra_tests = [' not in text:
    text += footer
path.write_text(text, encoding="utf-8")
Path(".github/scripts/fix_planned_filter_tests.py").unlink(missing_ok=True)
Path(".github/workflows/fix-planned-filter-tests.yml").unlink(missing_ok=True)
