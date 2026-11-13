"""Verify the live Streamlit pages and save actual browser screenshots."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from clean import EVIDENCE


def main():
    """Exercise all three pages and a category filter; fail on application errors."""
    errors=[]
    chrome=Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(chrome),headless=True)
        page=browser.new_page(viewport={'width':1550,'height':2400},device_scale_factor=1)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto('http://127.0.0.1:8501',wait_until='networkidle')
        page.get_by_text('Typical and slow resolution times in high-volume categories',exact=True).wait_for(timeout=60000)
        for label,filename,heading in [
            ('Outcomes','dashboard_outcomes.png','Typical and slow resolution times in high-volume categories'),
            ('Workflow patterns','dashboard_workflow.png','Repeated handoffs are an investigation signal'),
            ('Investigation priorities','dashboard_priorities.png','Start where investigative reach is substantial')]:
            page.get_by_text(label,exact=True).click()
            page.get_by_text(heading,exact=True).wait_for(timeout=60000)
            page.locator('[data-testid="stAppViewContainer"]').wait_for()
            page.locator('[data-testid="stDataFrame"]').first.wait_for()
            page.wait_for_timeout(4000)
            assert page.locator('[data-testid="stException"]').count()==0
            page.screenshot(path=str(EVIDENCE/filename),full_page=True)
        page.get_by_text('Outcomes',exact=True).click()
        page.get_by_text('Typical and slow resolution times in high-volume categories',exact=True).wait_for()
        page.get_by_role('combobox').first.click()
        page.get_by_role('combobox').first.fill('Category 34')
        page.get_by_role('option',name='Category 34',exact=True).click()
        page.wait_for_timeout(2000)
        assert page.get_by_text('498',exact=True).count()>=1
        assert page.locator('[data-testid="stException"]').count()==0
        contrasts={}
        # Check actual rendered contrast under both system themes: a fixed pale
        # card must remain readable even when the rest of Streamlit becomes dark.
        for mode in ['light','dark']:
            themed=browser.new_page(color_scheme=mode,viewport={'width':1550,'height':1800})
            themed.goto('http://127.0.0.1:8501',wait_until='networkidle')
            themed.get_by_text('Typical and slow resolution times in high-volume categories',exact=True).wait_for(timeout=60000)
            ratio=themed.locator('[data-testid="stMetric"]').first.evaluate('''el => {
                const luminance = color => {
                    const rgb = color.match(/[\\d.]+/g).slice(0,3).map(Number).map(v => {
                        v /= 255; return v <= 0.04045 ? v/12.92 : ((v+0.055)/1.055)**2.4;
                    });
                    return rgb[0]*0.2126+rgb[1]*0.7152+rgb[2]*0.0722;
                };
                const foreground=luminance(getComputedStyle(el.querySelector('[data-testid="stMetricValue"]')).color);
                const background=luminance(getComputedStyle(el).backgroundColor);
                return (Math.max(foreground,background)+0.05)/(Math.min(foreground,background)+0.05);
            }''')
            assert ratio>=4.5,(mode,ratio)
            contrasts[mode]=round(ratio,2)
            if mode=='dark':
                themed.wait_for_timeout(2000)
                themed.screenshot(path=str(EVIDENCE/'dashboard_outcomes_dark.png'),full_page=True)
            themed.close()
        browser.close()
    assert not errors,errors
    (EVIDENCE/'dashboard_validation.json').write_text(json.dumps(dict(pages_checked=3,category_filter_checked='Category 34: 498 incidents',metric_contrast_by_theme=contrasts,browser_errors=errors),indent=2),encoding='utf-8')
    print('Three screenshots saved; category filter and browser errors checked.')


if __name__=='__main__':
    main()
