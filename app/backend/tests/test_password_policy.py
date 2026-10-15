"""New-password rule; login remains compatible with existing passwords."""
import pytest
from pydantic import ValidationError
from backend.aicademiya.models import Register, ProvisionStudent, ChangePassword, Login, validate_new_password

@pytest.mark.parametrize('password', ['abcdefg1', 'ABCDEFG1', 'abc12345', 'abc1234!', 'a' * 511 + '1'])
def test_new_password_accepts_letters_and_digits_without_case_or_symbol_requirement(password):
    assert validate_new_password(password) == password
    assert Register(name='QA', email='qa@example.test', join_code='course', password=password).password == password
    assert ProvisionStudent(name='QA', email='qa@example.test', temporary_password=password).temporary_password == password
    assert ChangePassword(current_password='old', new_password=password).new_password == password

@pytest.mark.parametrize('password', ['abc1234', 'abcdefgh', '12345678', '!!!!!!!!', 'a' * 512 + '1'])
def test_new_password_rejects_short_or_missing_letter_digit(password):
    with pytest.raises(ValueError):validate_new_password(password)
    with pytest.raises(ValidationError):Register(name='QA', email='qa@example.test', join_code='course', password=password)
    with pytest.raises(ValidationError):ProvisionStudent(name='QA', email='qa@example.test', temporary_password=password)
    with pytest.raises(ValidationError):ChangePassword(current_password='old', new_password=password)

def test_login_does_not_revalidate_existing_password_policy():
    assert Login(email='qa@example.test', password='legacy-password').password == 'legacy-password'
