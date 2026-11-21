# BT-Batterytics

BT-Batterytics báo mức pin của thiết bị Bluetooth, ghi nhớ thời gian mỗi thiết bị kết nối giữa hai lần sạc và hiển thị thống kê.

Đây là bản sửa đổi của [BlueToothBatteryReport](https://github.com/haitun001/BlueToothBatteryReport) do haitun001 và cary-rowen phát triển (xem Ghi công và giấy phép bên dưới).

Hỗ trợ báo pin nhiều thiết bị, lần lượt đọc mọi thiết bị Bluetooth có thể phát hiện mức pin. Thứ tự: đã kết nối, không rõ, chưa kết nối.

## Phím tắt

- `NVDA+Shift+B` trên máy không có pin (máy để bàn), `NVDA+Alt+B` trên máy có pin (máy xách tay hoặc máy tính bảng) — Nhấn một lần để đọc trạng thái pin, hai lần để sao chép báo cáo vào bộ nhớ tạm, ba lần để mở bảng thiết lập.

NVDA+Shift+B là lệnh trạng thái pin của NVDA. Máy để bàn không có pin nên tiện ích dùng cử chỉ đó. Trên máy có pin, tiện ích dùng NVDA+Alt+B để giữ lệnh của NVDA. Lựa chọn được thực hiện khi NVDA khởi động theo thông tin Windows; nếu không xác định được thì coi như có pin. Đổi cử chỉ tại NVDA → Tùy chọn → Cử chỉ đầu vào, danh mục BT-Batterytics. Danh mục này cũng có lệnh “Mở thống kê pin Bluetooth”, mặc định chưa gán cử chỉ.

## Định dạng đọc

Khi có thông tin pin, mỗi thiết bị được đọc như sau:

- `tên thiết bị pin xx%`

Có thể hiện thêm loại kết nối và thời gian kết nối:

- `tên thiết bị (Classic) pin xx%`
- `tên thiết bị (LE) pin xx%`
- `tên thiết bị pin xx% (đã kết nối 2 giờ 5 phút)`

Nếu bạn đặt tên riêng cho thiết bị (xem Thống kê pin), tên đó được đọc thay tên Windows đặt.

## Thiết lập

Trang thiết lập riêng nằm tại NVDA → Tùy chọn → Thiết lập → BT-Batterytics.

### Thiết bị được báo cáo

- **Báo cáo thiết bị đã kết nối** — Đọc các thiết bị hiện đang kết nối (mặc định bật).
- **Báo cáo thiết bị chưa kết nối** — Đọc các thiết bị đã ghép đôi nhưng chưa kết nối.
- **Báo cáo thiết bị không rõ trạng thái** — Đọc các thiết bị không xác định được trạng thái kết nối. Bluetooth LE thường có trạng thái này.

### Thông tin đọc cho mỗi thiết bị

- **Hiện loại kết nối (Classic / LE)** — Thêm nhãn cho biết dùng Bluetooth Classic hay Bluetooth Low Energy.
- **Hiện thời lượng kết nối** — Đọc thời gian thiết bị đã kết nối.
- **Đọc tổng thời gian kết nối từ lần sạc gần nhất** — Chọn thời gian được đọc và bật đo (mặc định bật).
  - Chọn: tổng thời gian kết nối tính từ lần sạc gần nhất, được nhớ qua ngắt kết nối và khởi động lại NVDA; hoạt động cho Classic và LE.
  - Bỏ chọn: chỉ thời gian của phiên kết nối hiện tại do Windows báo. Windows chỉ cung cấp cho Classic nên LE không có thời gian ở chế độ này.
- **Hiện ước tính hộp sạc trong báo cáo** — Thêm số lần hộp còn sạc được tai nghe vào dòng báo cáo (mặc định tắt, xem Hộp sạc).

### Thống kê

- **Xem thống kê pin...** — Mở cửa sổ thống kê pin (xem bên dưới).
- **Số chu kỳ đã hoàn thành tối đa giữ lại cho mỗi thiết bị** — Từ 5 đến 5000, mặc định 500. Xóa chu kỳ cũ nhất khi vượt giới hạn.
- **Xóa chu kỳ đã hoàn thành cũ hơn số ngày này** — 0 giữ tất cả (mặc định).

### Cảnh báo

- **Bật cảnh báo pin yếu (mặc định cho mọi thiết bị)** — Báo khi pin của thiết bị đang kết nối thấp hơn ngưỡng của nó. Mỗi thiết bị theo thiết lập này trừ khi được đặt riêng (xem Cảnh báo). Hộp thoại cảnh báo pin yếu luôn hiển thị.
- **Ngưỡng pin yếu mặc định** — Phần trăm kích hoạt cảnh báo cho thiết bị chưa có ngưỡng riêng (5–50%, mặc định 20%).
- **Phương thức cảnh báo (cho mọi cảnh báo)** — Các hộp kiểm dùng kết hợp:
  - **Đọc cảnh báo** (mặc định chọn)
  - **Phát hai tiếng bíp**
  - **Phát âm thanh cảnh báo** (xem Âm thanh cảnh báo)
- **Mở thư mục âm thanh...** — Mở thư mục tệp âm cảnh báo để thay thế.
- **Cảnh báo mức pin giảm: cảnh báo mỗi khi pin giảm từng này điểm phần trăm** — Từ 1 đến 50, mặc định 10.
- **Kiểm tra thay đổi kết nối thiết bị sau mỗi số giây này** — Từ 5 đến 300, mặc định 15. Chỉ dùng khi có thiết bị bật cảnh báo kết nối hoặc ngắt kết nối.

## Theo dõi thời gian kết nối

Tiện ích ghi thời gian mỗi thiết bị kết nối giữa hai lần sạc, giúp biết thời lượng thực tế mỗi lần sạc. Chạy nền và được điều khiển bằng **Đọc tổng thời gian kết nối từ lần sạc gần nhất**.

- Bắt đầu theo dõi khi tiện ích thấy thiết bị lần đầu ở bất kỳ mức pin nào. Vì vậy chu kỳ đầu có thể ngắn hơn thực tế nếu lúc đó pin chưa đầy.
- Chỉ tính thời gian thiết bị được thấy là đã kết nối. Không tính lúc ngắt kết nối nhưng giữ tổng đã tính.
- Phát hiện sạc lại khi pin cao hơn ít nhất 15 điểm phần trăm so với mức thấp nhất trong chu kỳ. Cũng dùng được với thiết bị không bao giờ đạt 100%. Lưu chu kỳ đã hoàn thành và tính lại từ không. Không tính khi mức pin tăng (đang sạc).
- Nếu Windows báo thời gian kết nối Classic dài hơn tiện ích đã tính, dùng giá trị dài hơn. LE không có giá trị đó nên tổng chỉ bao gồm thời gian tiện ích quan sát được.
- Không tính khoảng gián đoạn giữa hai lần quan sát dài hơn 15 phút (ví dụ máy ngủ).
- Chu kỳ ngắn hơn 30 phút không được lưu thành chu kỳ đã hoàn thành.
- Nhận diện theo địa chỉ Bluetooth, không phải tên. Hai thiết bị trùng tên có bản ghi riêng; đổi tên trong Windows vẫn giữ dữ liệu.
- Có thể dừng đo thiết bị (xem Thống kê pin). Dữ liệu được giữ, thời gian kết nối khi đó dùng giá trị Windows báo, nếu có.

### Thiết bị không luôn kết nối

Một số thiết bị vẫn bật nhưng hiếm khi kết nối máy tính. Ví dụ bàn phím ba chế độ dùng đầu thu 2,4 GHz, chỉ thỉnh thoảng kết nối Bluetooth để kiểm tra pin. Thời gian kết nối rất ngắn và chu kỳ dưới 30 phút kết nối không được lưu, nên không có bản ghi hữu ích. Với thiết bị này, chọn **Tính thời gian đã trôi qua** trong trình đơn Đo thời gian của thiết bị ở cửa sổ thống kê. Mặc định tắt, đặt riêng từng thiết bị.

Khi bật:

- Thời gian chu kỳ chạy từ lúc sạc lại đến lần cuối thấy mức pin giảm. Không tính đến lần bạn kiểm tra tiếp, vì mức pin chỉ biết khi đọc và Windows có thể hiển thị giá trị cũ cho thiết bị chưa kết nối.
- Phát hiện sạc lại ở lần đọc pin đầu tiên sau đó. Thời điểm sạc được lấy ở giữa lần đọc cuối trước sạc và lần này.
- Các ước tính (dùng khi sạc đầy, tốc độ hao pin, thời gian còn lại, xu hướng) và cột Khoảng cách giữa các lần sạc dùng thời gian này; từ hai ngày hiển thị bằng ngày. Chu kỳ đầu bắt đầu khi tiện ích thấy thiết bị lần đầu, bất kể mức pin.
- Dòng báo cáo hiển thị thời gian từ lần sạc gần nhất thay thời gian kết nối.
- Mỗi chu kỳ nhớ cách tính thời gian. Thống kê chỉ dùng chu kỳ tính theo cách thiết bị đang dùng. Các chu kỳ khác vẫn ở danh sách với cách tính trong cột Cách tính thời gian.
- Đổi cách tính sẽ bắt đầu lại chu kỳ hiện tại.

Thỉnh thoảng đọc pin thiết bị này: kết nối Bluetooth và nhấn phím tắt. Đọc càng thưa, ước tính càng kém chính xác; nếu sạc hai lần giữa hai lần đọc, hai chu kỳ bị tính thành một.

### Thiết bị không giảm đến 0%

Một số thiết bị báo mức pin giảm không đều. Ví dụ bàn phím giữ ở 100% rất lâu rồi giảm nhanh, ngừng hoạt động ở 55% hoặc 60%. Bạn học cách sạc sớm, như ở 70%, để an toàn. Ước tính thống kê (Dùng khi sạc đầy, Thời gian còn lại) giả định pin giảm đều đến 0%, nên quá dài với thiết bị này: thời lượng thực tế giữa các lần bạn sạc ngắn hơn nhiều.

Chọn **Mức pin thường sạc lại...** trong trình đơn Đo thời gian và nhập mức bạn sạc, ví dụ 70. Mặc định tắt (0), đặt riêng từng thiết bị.

Khi bật:

- Dùng khi sạc đầy (ước tính) thành thời gian từ pin đầy đến mức bạn đặt, tức thời gian giữa các lần sạc.
- Thời gian còn lại (ước tính) thành thời gian trước khi pin đến mức đó; bằng không nếu đã bằng hoặc thấp hơn.
- Tốc độ hao pin, thời gian chu kỳ và phát hiện sạc không đổi.
- Cột Đo thời gian ở tóm tắt thêm mức pin, ví dụ “bật, sạc lại ở 70%”.

Giữ tắt với thiết bị có pin giảm đều. Ước tính vẫn thô vì pin giảm không đều; số đáng tin nhất là thời gian thực giữa các lần sạc: Trung bình, Ngắn nhất, Dài nhất và Khoảng cách giữa các lần sạc.

## Thống kê pin

**Xem thống kê pin...** trong bảng thiết lập mở cửa sổ hai danh sách. Lệnh “Mở thống kê pin Bluetooth” trong Cử chỉ đầu vào mở trực tiếp. Cửa sổ vẫn hiện bản ghi khi tắt đo.

Thiết bị xếp như báo cáo đọc: đã kết nối, không rõ, chưa kết nối, rồi theo tên. Thiết bị không có trong lần quét gần nhất đứng cuối.

### Tóm tắt từng thiết bị

Mỗi thiết bị một hàng:

- **Trạng thái** — Trạng thái kết nối ở lần quét gần nhất.
- **Đo thời gian** — Tắt, bật hay bật theo thời gian đã trôi qua. Thêm mức pin thường sạc lại khi đặt, ví dụ “sạc lại ở 70%”.
- **Cảnh báo** — Cảnh báo đang bật, như “pin yếu 20%, mức pin giảm” hoặc “không có”.
- **Chu kỳ** — Số chu kỳ đã hoàn thành.
- **Trung bình**, **Ngắn nhất**, **Dài nhất** — Thời gian kết nối của các chu kỳ đã hoàn thành.
- **Dùng khi sạc đầy (ước tính)** — Ước tính thời lượng đầy pin, tính theo lượng pin mỗi chu kỳ dùng, cho phép so sánh chu kỳ không bắt đầu ở 100%.
- **Tốc độ hao pin** — Điểm phần trăm pin dùng mỗi giờ kết nối, hoặc mỗi ngày với thiết bị hao chậm.
- **Khoảng cách giữa các lần sạc** — Thời gian trung bình giữa hai lần sạc.
- **Lần sạc gần nhất** — Khi phát hiện lần sạc lại gần nhất.
- **Xu hướng** — So sánh 3 chu kỳ mới nhất với trước đó, như “ngắn hơn 12%” hoặc “ổn định” (chênh dưới 5%). Cần ít nhất 4 chu kỳ.
- **Thời gian còn lại (ước tính)** — Thời gian kết nối còn lại theo tốc độ hao thông thường, từ mức pin thấy gần nhất.
- **Hộp đã dùng (số lần sạc ước tính)** và **Hộp còn lại (số lần sạc ước tính)** — Số lần hộp đã sạc và còn sạc được, chỉ cho thiết bị có hộp (xem Hộp sạc). Thêm hai cột khi bật hộp sạc lần đầu; có thể ẩn.

### Chu kỳ

Ban đầu chỉ hiện chu kỳ đang diễn ra (“hiện tại”) cho mỗi thiết bị. Chu kỳ đã hoàn thành được thu gọn, mới nhất trước. Nhấn Space trên bất kỳ hàng của thiết bị, nhấp đúp hoặc dùng trình đơn ngữ cảnh (phím Applications) để mở rộng; làm lại để thu gọn. NVDA đọc “Đã mở rộng” hoặc “Đã thu gọn”. Các cột:

- **Chu kỳ** — Số chu kỳ.
- **Trạng thái hiển thị** — “đã thu gọn” hoặc “đã mở rộng” trên hàng chu kỳ hiện tại; trống nếu chưa có chu kỳ hoàn thành.
- **Thời lượng** — Thời gian kết nối của chu kỳ.
- **Pin** — Mức đầu và thấp nhất, ví dụ “100% đến 23%”.
- **Tốc độ hao pin** — Điểm phần trăm dùng mỗi giờ trong chu kỳ.
- **Dùng khi sạc đầy (ước tính)** — Ước tính thời lượng đầy pin của chu kỳ.
- **Kết thúc** — Khi phát hiện lần sạc kết thúc chu kỳ.
- **Cách tính thời gian** — Thời gian kết nối hay thời gian đã trôi qua (xem Thiết bị không luôn kết nối). Thêm lần đầu dùng thời gian đã trôi qua, có thể ẩn.

Ước tính bỏ qua chu kỳ dùng dưới 10 điểm phần trăm pin vì mức pin Bluetooth thường báo theo bước lớn. Ô trống nghĩa là chưa đủ dữ liệu. Càng nhiều chu kỳ, ước tính càng đáng tin.

## Lệnh trong cửa sổ thống kê

Hai danh sách dùng chung lệnh. Phần lớn có phím; tất cả nằm trong trình đơn ngữ cảnh (Applications). Lệnh mở trình đơn con hoặc hộp thoại đứng trước, lệnh có phím đứng sau.

### Đo thời gian

Trình đơn con có hai mục đánh dấu cho thiết bị:

- **Đo thời gian thiết bị này** — Dừng hoặc bắt đầu lại đo, giữ dữ liệu.
- **Tính thời gian đã trôi qua (cho thiết bị không luôn kết nối)** — Tính từ lần sạc gần nhất thay thời gian kết nối. Xem Thiết bị không luôn kết nối.
- **Mức pin thường sạc lại...** — Mức bạn thường sạc với thiết bị báo pin không đều. Xem Thiết bị không giảm đến 0%.

### Cảnh báo

Cảnh báo của thiết bị. Xem Cảnh báo bên dưới.

### Chọn

Đảo trạng thái chọn hàng hiện tại (**Control+Space**), Chọn tất cả (**Control+A**), Bỏ chọn tất cả, Đảo vùng chọn, Chọn các hàng của thiết bị này. Có thể chọn nhiều hàng như danh sách thường; NVDA đọc “đã chọn”. Chỉ dùng mũi tên sẽ chọn riêng hàng hiện tại. Để tạo vùng chọn, di chuyển bằng Control+mũi tên và nhấn Control+Space từng hàng.

### Sắp xếp

Không có phím. Chọn thứ tự thiết bị (thứ tự báo cáo, tên, số chu kỳ, thời gian trung bình, ước tính đầy pin, lần sạc gần nhất, thời gian chu kỳ hiện tại, tốc độ hao pin hoặc thủ công) và thứ tự chu kỳ hoàn thành (mới nhất, cũ nhất, dài nhất, ngắn nhất trước hoặc thủ công). Mục được đánh dấu đang dùng và lựa chọn được nhớ. Với **Thủ công**, bạn tự quyết thứ tự (xem Di chuyển thiết bị hoặc chu kỳ).

### Di chuyển thiết bị hoặc chu kỳ

**Control+Shift+Mũi tên lên** và **Control+Shift+Mũi tên xuống**. Cần sắp xếp thủ công: chọn Thủ công trong Sắp xếp, mục Sắp xếp thiết bị theo để di chuyển thiết bị; mục Sắp xếp chu kỳ theo để di chuyển chu kỳ. Lần đầu chọn Thủ công cho thiết bị, thứ tự đang dùng trở thành thứ tự riêng.

- Trong tóm tắt và hàng chu kỳ hiện tại, phím di chuyển thiết bị cùng mọi hàng.
- Trên chu kỳ hoàn thành của thiết bị đã mở rộng, phím di chuyển chu kỳ trong các chu kỳ hoàn thành của thiết bị đó.

NVDA đọc vị trí mới, như “2 trên 5”; bíp nghĩa là hàng đã ở cuối hướng đó. Thứ tự được nhớ. Thiết bị thấy lần đầu và chu kỳ vừa hoàn thành được đặt đầu.

### Di chuyển danh sách

**Control+Shift+Mũi tên trái** và **Control+Shift+Mũi tên phải** đưa danh sách đang có tiêu điểm ra trước hoặc sau danh sách kia. Cửa sổ mở ở danh sách đầu tiên, nên bạn chọn danh sách xem nhiều nhất. Thứ tự được nhớ.

### Chọn cột

Không có phím. Mở danh sách hộp kiểm cho từng cột tùy chọn của hai danh sách. Cột Thiết bị và Chu kỳ luôn hiện. Nhấn Control+Shift+Mũi tên lên hoặc xuống trên cột để di chuyển; thứ tự dùng khi hiện, sao chép và xuất. Lựa chọn được nhớ.

### Mở rộng và thu gọn

**Space** ở danh sách chu kỳ hiện hoặc ẩn các chu kỳ đã hoàn thành của thiết bị.

### Đổi tên thiết bị

**F2** đặt tên riêng cho thiết bị của hàng hiện tại. Để trống hoặc nhập tên gốc để trở về tên Windows đặt. Tên dùng trong thống kê, báo cáo đọc và cảnh báo.

### Sao chép

- **Control+C** sao chép hàng hiện tại.
- **Control+Shift+C** sao chép mọi thứ về thiết bị hiện tại (tóm tắt và mọi chu kỳ, kể cả đang thu gọn).

Chỉ sao chép cột đang hiện dưới dạng cặp “Tiêu đề: giá trị”.

### Đánh dấu hộp đã sạc

**Control+Shift+R**, chỉ với thiết bị có hộp sạc. Báo tiện ích rằng bạn đã sạc hộp để đếm số lần sạc đã dùng từ không. Xem Hộp sạc.

### Xuất

**Control+E** mở trình đơn Xuất, gồm:

- **Nội dung xuất** — Hàng được chọn, thiết bị hiện tại hoặc mọi hàng của danh sách. Mục đánh dấu đang dùng.
- **Gồm các giá trị chi tiết** — Mặc định chọn và được nhớ. Thêm định danh (địa chỉ và hai tên) và giá trị chính xác vào cột: giây, phần trăm pin, điểm phần trăm đã dùng, ngày ISO 8601. Nếu bỏ chọn, chỉ xuất cột đang hiện.
- **Sao chép vào bộ nhớ tạm dưới dạng** và **Lưu vào tệp dưới dạng** — Văn bản thuần, bảng Markdown, CSV, giá trị phân cách bằng tab (dán vào bảng tính), JSON (số vẫn là số) hoặc bảng HTML. CSV lưu với dấu thứ tự byte để Excel hiện đúng mọi ký tự.
- **Mở báo cáo HTML trong trình duyệt** — Tạo trang có tiêu đề và bảng rồi mở trong trình duyệt web.

Có thể gửi ngay dữ liệu xuất cho người khác hoặc công cụ AI.

### Làm mới

**F5** quét lại thiết bị và cập nhật cửa sổ; nếu không, cửa sổ chỉ phản ánh lúc mở.

### Xóa

- **Control+Delete** xóa hàng hiện tại; nếu chọn nhiều hàng, xóa tất cả hàng được chọn.
- **Control+Shift+Delete** xóa thiết bị của hàng hiện tại cùng toàn bộ dữ liệu.

Luôn hỏi xác nhận Có hoặc Không trước. Trên chu kỳ đang diễn ra, “xóa” bắt đầu lại chu kỳ từ không. Trong tóm tắt, xóa hàng là xóa thiết bị. Nếu bật đo, thiết bị đã xóa bắt đầu lại từ không ở lần kiểm tra sau.

## Cảnh báo

Mỗi thiết bị có thể có các cảnh báo sau, chọn riêng trong cửa sổ thống kê (trình đơn ngữ cảnh, **Cảnh báo**; cột Cảnh báo trong tóm tắt hiện mục đang bật). Mọi cảnh báo dùng phương thức đã chọn trong thiết lập.

### Pin yếu

Báo một lần khi pin thiết bị đang kết nối yếu, đến khi pin phục hồi mới có thể báo lại. Cũng hiện hộp thoại cảnh báo. Trong trình đơn Cảnh báo, **Ngưỡng pin yếu...** mở ba lựa chọn:

- **Dùng mặc định** — Theo **Bật cảnh báo pin yếu** và ngưỡng mặc định trong thiết lập. Nếu tắt ở thiết lập, thiết bị không báo.
- **Dùng ngưỡng riêng** — Từ 5 đến 50%. Thiết bị vẫn báo ở mức này dù tắt cảnh báo pin yếu trong thiết lập.
- **Không bao giờ cảnh báo cho thiết bị này** — Không báo pin yếu, bất kể thiết lập.

### Mức pin giảm

Mặc định tắt. Báo mỗi khi pin giảm số điểm phần trăm đã đặt kể từ cảnh báo trước, tính từ mức lúc thấy thiết bị lần đầu và tính lại khi mức tăng (sạc). Bước báo tùy thiết bị: có loại mỗi 1%, loại khác mỗi 10% hoặc hơn. Với mặc định 10 điểm, thiết bị báo bước 10% cảnh báo mỗi bước. Nếu cùng thiết bị có cảnh báo pin yếu trong cùng lần kiểm tra, chỉ phát cảnh báo pin yếu.

### Thiết bị kết nối và thiết bị ngắt kết nối

Mặc định tắt. Báo khi chuyển giữa đã kết nối và chưa kết nối. Như cách tính thời gian, coi là kết nối trừ khi biết đã ngắt; vì vậy LE (trạng thái không rõ) chỉ báo ngắt nếu Windows báo đã ngắt. Lần kiểm tra đầu sau khi NVDA khởi động chỉ ghi nhớ trạng thái. Kiểm tra lại mỗi vài giây (xem thiết lập).

### Hộp sạc

Cho tai nghe không dây hoàn toàn đi kèm hộp. Mặc định tắt, riêng từng thiết bị. Windows báo pin tai nghe chứ không phải hộp, nên tiện ích ước tính số lần hộp đã sạc tai nghe. **Hộp sạc...** trong trình đơn Cảnh báo mở các trường:

- **Cảnh báo về hộp sạc** — Bật ước tính và cảnh báo cho thiết bị.
- **Thời lượng tai nghe mỗi lần sạc (giờ)** và **Tổng thời lượng kể cả hộp sạc (giờ)** — Ví dụ 10 giờ và 52 giờ. Hộp sạc được khoảng 4,2 lần: 52 chia 10 trừ lần đầu sẵn trong tai nghe.
- **Dùng thống kê** — Điền thời lượng mỗi lần sạc bằng ước tính đầy pin trong thống kê, làm tròn đến nửa giờ.
- **Cảnh báo khi số lần sạc còn lại ít hơn** — Mặc định 1.

Mỗi khi thấy tai nghe sạc lại, tiện ích cộng điểm phần trăm tăng vào số lần sạc đã dùng (100 điểm là một lần). Cảnh báo khi pin tai nghe yếu đến ngưỡng riêng hoặc mặc định và ước tính hộp còn ít lần sạc hơn trường trên. Đó là lúc sạc hộp cùng tai nghe. Chỉ báo một lần đến khi pin tai nghe phục hồi, đồng thời hiện hộp thoại như cảnh báo pin yếu.

Sau cảnh báo, lần tiếp theo thấy tai nghe sạc lại (bạn lấy khỏi hộp và kết nối), tiện ích hỏi có sạc hộp luôn không. **Có** tính lại từ không. **Không**, câu trả lời mặc định, tiếp tục tính.

Bất cứ lúc nào cũng có thể dùng **Đánh dấu hộp đã sạc** (Control+Shift+R trong thống kê) để tính lại. Mỗi lần đánh dấu, tiện ích nhớ số lần hộp đã sạc trong vòng đó. Từ vòng hoàn thành thứ ba, dùng giá trị điển hình của năm vòng gần nhất thay thời lượng bạn nhập.

Giới hạn ước tính:

- Chỉ tốt khi tai nghe chủ yếu dùng với máy này. Sạc khi dùng với thiết bị khác như điện thoại không được tính, khiến hộp có vẻ đầy hơn thực tế.
- Bạn phải báo mỗi lần sạc hộp bằng cách trả lời hoặc đánh dấu, vì tiện ích không tự biết.
- Phải đo thời gian kết nối thiết bị, như thống kê.
- Đây là ước tính, không phải phép đo.

### Âm thanh cảnh báo

Giọng nói đọc ví dụ “tên thiết bị đã kết nối” hoặc “tên thiết bị pin 80%”; hai tiếng bíp giống nhau cho mọi cảnh báo; âm riêng là tệp .wav trong thư mục `sounds` của tiện ích (cạnh `globalPlugins`). Dùng **Mở thư mục âm thanh...** trong thiết lập và thay tệp để đổi âm. Thiếu tệp thì phát bíp. Nhiều cảnh báo cùng lúc phát âm lần lượt. Các tệp:

- `lowBattery.wav`
- `levelDrop.wav`
- `deviceConnected.wav`
- `deviceDisconnected.wav`
- `chargingCase.wav`

## Giám sát nền

Khi bật cảnh báo pin yếu, theo dõi thời gian kết nối hoặc bất kỳ cảnh báo của thiết bị, tiện ích kiểm tra pin nền mỗi 5 phút. Khi có cảnh báo kết nối/ngắt kết nối, kiểm tra kết nối thường xuyên hơn (mỗi vài giây, xem thiết lập); phần còn lại vẫn mỗi 5 phút.

## Dữ liệu và thiết lập

Bản ghi lưu trong `btBatterytics_usage.json` ở thư mục cấu hình người dùng NVDA. Sao chép tệp để sao lưu. Xóa tệp khi NVDA không chạy để bắt đầu lại.

Lần đầu chạy, BT-Batterytics tiếp nhận dữ liệu tên cũ: sao chép từ `blueToothBatteryReport_usage.json` (giữ nguyên tệp cũ) và lấy thiết lập từ phần cũ. Bản ghi trước thời nhận diện bằng địa chỉ được chuyển sang địa chỉ của thiết bị cùng tên khi thấy lần đầu.

## Ghi công âm thanh

Âm thanh đi kèm từ Pixabay:

- `levelDrop.wav` — Hiệu ứng của [Vadim](https://pixabay.com/users/vadim_makes_sound-54823268/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=614159) từ [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=614159)
- `lowBattery.wav` — Hiệu ứng của [Shagor Miah](https://pixabay.com/users/u_31vnwfmzt6-31480456/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=126627) từ [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=126627)
- `deviceConnected.wav` — Hiệu ứng của [juniorsoundays](https://pixabay.com/users/juniorsoundays-19205462/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527856) từ [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527856)
- `deviceDisconnected.wav` — Hiệu ứng của [juniorsoundays](https://pixabay.com/users/juniorsoundays-19205462/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527837) từ [Pixabay](https://pixabay.com/sound-effects/?utm_source=link-attribution&utm_medium=referral&utm_campaign=music&utm_content=527837)

## Ghi công và giấy phép

BT-Batterytics dựa trên [BlueToothBatteryReport](https://github.com/haitun001/BlueToothBatteryReport), bản quyền (C) haitun001 và cary-rowen, được NVDATH sửa đổi năm 2026. Dùng GNU General Public License phiên bản 2 như bản gốc.

### Cách thực hiện sửa đổi

Ý tưởng, quyết định về hành vi tiện ích và mọi thử nghiệm với NVDA do NVDATH thực hiện. Mọi sửa đổi mã nguồn gốc do Claude, trợ lý AI của Anthropic, viết theo chỉ dẫn NVDATH. Mã không được lập trình viên viết tay, vì vậy hãy báo mọi vấn đề cho NVDATH.

## Phiên bản NVDA hỗ trợ

- Tối thiểu: `2025.1.0`
- Đã thử đến: `2026.3.1`

