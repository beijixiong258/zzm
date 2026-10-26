package zzm.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

@Data
public class LegacyRecord {
    @TableId(type = IdType.ASSIGN_UUID)
    private String id;
    private String sourceTable;
    private String sourceKey;
    private String payloadJson;
}
