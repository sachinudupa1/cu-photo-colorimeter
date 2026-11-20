from backend.app.model_service import select_calibration_method


def make_rows(concs, red_values, green_values, role='standard'):
    rows=[]
    for i,(c,r,g) in enumerate(zip(concs,red_values,green_values)):
        rows.append({
            'concentration': float(c), 'A_R': float(r), 'A_R_srgb': float(r),
            'A_G': float(g), 'A_G_srgb': float(g), 'A_B': float(g), 'A_B_srgb': float(g),
            'role': role, 'sample_id': f'{role}-{i}'
        })
    return rows


def test_method_selector_uses_validation_mae_when_validation_is_diverse():
    concentrations=[1,2,3,4,5]
    standards=make_rows(concentrations,[.1,.2,.3,.4,.5],[.03,.06,.09,.12,.15])
    validation=make_rows([6,7,8],[.80,.50,1.00],[.18,.21,.24],'validation')
    calibration, method, score, comparison, status=select_calibration_method(
        standards,validation,'unit',0.8
    )
    assert method['feature']=='A_G'
    assert status=='selected_by_validation_mae'
    assert score['mae'] < 1e-8
    assert sum(item['selected'] for item in comparison)==1
    assert calibration.channel=='G'


def test_method_selector_keeps_red_baseline_without_enough_validation_levels():
    standards=make_rows([1,2,3,4],[.1,.2,.3,.4],[.02,.04,.06,.08])
    validation=make_rows([5,6],[.5,.6],[.10,.12],'validation')
    _,method,score,comparison,status=select_calibration_method(standards,validation,'unit',0.8)
    assert method['feature']=='A_R'
    assert status=='baseline_only_insufficient_validation'
    assert len(comparison)==1
