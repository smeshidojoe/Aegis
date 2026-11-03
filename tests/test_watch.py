import os
import time

from aegis.vault import watch

CSV = "name,url,username,password\nA,https://a.com,me,pw\n"


def test_only_new_csv_is_found_and_deleted(tmp_path):
    old_csv = tmp_path / "old passwords.csv"
    old_csv.write_text(CSV)
    other = tmp_path / "photo.jpg"
    other.write_bytes(b"jpg")
    waiter = watch.Waiter([str(tmp_path)])

    new_txt = tmp_path / "notes.txt"
    new_txt.write_text("x")
    new_csv = tmp_path / "Chrome Passwords.csv"
    new_csv.write_text(CSV)
    found = waiter.poll()
    assert found == [(str(tmp_path), str(new_csv))]
    assert waiter.poll() == []                      # второй раз не отдаётся

    expected = watch.fingerprint(str(new_csv))
    assert watch.safe_delete(str(new_csv), str(tmp_path), expected)
    assert not new_csv.exists()
    assert old_csv.exists() and other.exists() and new_txt.exists()


def test_changed_file_is_not_deleted(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(CSV)
    expected = watch.fingerprint(str(path))
    time.sleep(0.01)
    path.write_text(CSV + "B,https://b.com,me,pw2\n")
    assert not watch.safe_delete(str(path), str(tmp_path), expected)
    assert path.exists()


def test_refuses_outside_folder_and_non_csv(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    inner = sub / "x.csv"
    inner.write_text(CSV)
    assert not watch.safe_delete(str(inner), str(tmp_path), watch.fingerprint(str(inner)))
    txt = tmp_path / "x.txt"
    txt.write_text(CSV)
    assert not watch.safe_delete(str(txt), str(tmp_path), watch.fingerprint(str(txt)))
    assert inner.exists() and txt.exists()


def test_old_file_with_new_name_ignored(tmp_path):
    waiter = watch.Waiter([str(tmp_path)])
    path = tmp_path / "late.csv"
    path.write_text(CSV)
    os.utime(path, (time.time() - 3600, time.time() - 3600))   # старый файл, принесли копией
    assert waiter.poll() == []
